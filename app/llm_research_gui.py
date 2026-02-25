"""
LLM Research Engine GUI Integration
Provides user interface components for the LLM-powered research system.
"""

import json
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, scrolledtext, ttk
from typing import Any, Dict, List, Optional

try:
    from llm_research_engine import (
        AnalysisType,
        LLMResearchEngine,
        SignalStrength,
        TradeSignal,
        get_research_engine,
    )

    RESEARCH_ENGINE_AVAILABLE = True
except ImportError as e:
    RESEARCH_ENGINE_AVAILABLE = False
    print(f"Warning: LLM Research Engine not available - {e}")

    # Define fallback classes to prevent NameError
    class TradeSignal:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class SignalStrength:
        pass

    class AnalysisType:
        pass


class ResearchEngineGUI:
    """GUI interface for LLM Research Engine."""

    def __init__(self, parent, config: Dict = None):
        self.parent = parent
        self.config = config or {}

        # Initialize research engine
        if RESEARCH_ENGINE_AVAILABLE:
            self.engine = get_research_engine(config)
        else:
            self.engine = None

        # GUI state
        self.auto_refresh = tk.BooleanVar(value=False)
        self.refresh_interval = tk.StringVar(value="10")  # minutes
        self.current_symbols = []

        # Model cache for OpenAI models
        self.available_models = ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"]  # fallback
        self.models_loaded = False

        # Background threads
        self.refresh_thread = None
        self.analysis_thread = None
        self.running = False

        self.setup_gui()

    def fetch_openai_models(self):
        """Fetch available OpenAI models dynamically."""
        if not RESEARCH_ENGINE_AVAILABLE or self.models_loaded:
            return self.available_models

        try:
            import openai

            # Try to get API key from entry or config
            api_key = None
            if hasattr(self, "api_key_entry") and self.api_key_entry.get().strip():
                api_key = self.api_key_entry.get().strip()
            elif self.config.get("openai_api_key"):
                api_key = self.config.get("openai_api_key")

            if not api_key:
                print("No OpenAI API key available, using fallback models")
                return self.available_models

            # Initialize OpenAI client
            client = openai.OpenAI(api_key=api_key)

            # Fetch models
            models_response = client.models.list()
            all_models = [model.id for model in models_response.data]

            # Filter to ChatGPT models only
            chat_models = []
            for model in all_models:
                if any(prefix in model for prefix in ["gpt-4", "gpt-3.5"]):
                    chat_models.append(model)

            # Sort models (put gpt-4 variants first, then 3.5)
            chat_models.sort(
                key=lambda x: (
                    "0" if "gpt-4" in x else "1",  # gpt-4 models first
                    "0" if "turbo" in x else "1",  # turbo models first within category
                    x,  # alphabetical within sub-categories
                )
            )

            if chat_models:
                self.available_models = chat_models
                self.models_loaded = True
                print(f"Loaded {len(chat_models)} OpenAI models")
            else:
                print("No compatible ChatGPT models found, using fallback")

        except Exception as e:
            print(f"Failed to fetch OpenAI models: {e}")
            # Keep fallback models

        return self.available_models

    def update_model_combobox(self):
        """Update model combobox with latest models."""
        if hasattr(self, "model_combo"):
            current_selection = self.model_combo.get()
            models = self.fetch_openai_models()
            self.model_combo["values"] = models

            # Restore selection if still available, otherwise pick first gpt-4 model
            if current_selection in models:
                self.model_combo.set(current_selection)
            else:
                gpt4_models = [m for m in models if "gpt-4" in m]
                if gpt4_models:
                    self.model_combo.set(gpt4_models[0])
                elif models:
                    self.model_combo.set(models[0])

    def setup_gui(self):
        """Setup the research engine GUI."""
        try:
            # Create main research frame
            self.research_frame = ttk.Frame(self.parent)
            self.research_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            if not RESEARCH_ENGINE_AVAILABLE:
                # Show message about unavailable research engine
                ttk.Label(
                    self.research_frame,
                    text="LLM Research Engine Dependencies Missing\n\nRequired modules:\n- OpenAI Python library\n- SQLAlchemy (optional)\n\nInstall with: pip install openai sqlalchemy",
                    font=("TkDefaultFont", 10),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
                return

            # Create notebook for tabs
            self.notebook = ttk.Notebook(self.research_frame)
            self.notebook.pack(fill=tk.BOTH, expand=True)

            # Create tabs with error handling
            try:
                self.create_market_analysis_tab()
            except Exception as e:
                print(f"Error creating market analysis tab: {e}")

            try:
                self.create_trade_signals_tab()
            except Exception as e:
                print(f"Error creating trade signals tab: {e}")

            try:
                self.create_research_reports_tab()
            except Exception as e:
                print(f"Error creating research reports tab: {e}")

            try:
                self.create_settings_tab()
            except Exception as e:
                print(f"Error creating settings tab: {e}")

            # Status bar
            self.status_bar = ttk.Frame(self.research_frame)
            self.status_bar.pack(fill=tk.X, pady=(5, 0))

            self.status_label = ttk.Label(self.status_bar, text="Ready")
            self.status_label.pack(side=tk.LEFT)

            self.engine_status = ttk.Label(
                self.status_bar,
                text="Engine: " + ("Available" if self.engine else "Not Available"),
                foreground="green" if self.engine else "red",
            )
            self.engine_status.pack(side=tk.RIGHT)

        except Exception as e:
            print(f"Error setting up research GUI: {e}")
            # Show error in the GUI
            try:
                ttk.Label(
                    self.research_frame,
                    text=f"LLM Research GUI Error\n\n{str(e)}\n\nCheck console for details.",
                    font=("TkDefaultFont", 10),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
            except:
                pass

    def create_market_analysis_tab(self):
        """Create market analysis tab."""
        try:
            self.analysis_tab = ttk.Frame(self.notebook)
            self.notebook.add(self.analysis_tab, text="Market\nAnalysis")

            # Controls frame
            controls_frame = ttk.LabelFrame(self.analysis_tab, text="Analysis Controls")
            controls_frame.pack(fill=tk.X, padx=5, pady=5)

            # Symbol input
            symbol_frame = ttk.Frame(controls_frame)
            symbol_frame.pack(fill=tk.X, padx=5, pady=2)

            ttk.Label(symbol_frame, text="Symbols:").pack(side=tk.LEFT)
            self.symbol_entry = ttk.Entry(symbol_frame, width=50, font=("Consolas", 9))
            self.symbol_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
            self.symbol_entry.insert(0, "BTCUSDT,ETHUSDT,ADAUSDT,BNBUSDT,XRPUSDT")

            # Control buttons
            button_frame = ttk.Frame(controls_frame)
            button_frame.pack(fill=tk.X, padx=5, pady=2)

            self.analyze_btn = ttk.Button(
                button_frame, text="Analyze Market", command=self.run_market_analysis
            )
            self.analyze_btn.pack(side=tk.LEFT)

            self.clear_analysis_btn = ttk.Button(
                button_frame, text="Clear", command=self.clear_analysis
            )
            self.clear_analysis_btn.pack(side=tk.LEFT, padx=(5, 0))

            # Auto-refresh controls
            auto_frame = ttk.Frame(button_frame)
            auto_frame.pack(side=tk.RIGHT)

            self.auto_refresh_check = ttk.Checkbutton(
                auto_frame,
                text="Auto-refresh every",
                variable=self.auto_refresh,
                command=self.toggle_auto_refresh,
            )
            self.auto_refresh_check.pack(side=tk.LEFT)

            self.refresh_interval_spinbox = ttk.Spinbox(
                auto_frame, from_=1, to=60, width=5, textvariable=self.refresh_interval
            )
            self.refresh_interval_spinbox.pack(side=tk.LEFT, padx=(5, 0))

            ttk.Label(auto_frame, text="min").pack(side=tk.LEFT)

            # Analysis results
            results_frame = ttk.LabelFrame(self.analysis_tab, text="Analysis Results")
            results_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            # Create treeview for analysis results
            columns = (
                "Symbol",
                "Price",
                "Change %",
                "RSI",
                "Signal",
                "Sentiment",
                "Last Updated",
            )
            self.analysis_tree = ttk.Treeview(
                results_frame, columns=columns, show="headings", height=10
            )

            # Setup columns
            for col in columns:
                self.analysis_tree.heading(col, text=col)
                if col == "Symbol":
                    self.analysis_tree.column(col, width=80, anchor=tk.W)
                elif col in ["Price", "Change %"]:
                    self.analysis_tree.column(col, width=100, anchor=tk.E)
                elif col == "RSI":
                    self.analysis_tree.column(col, width=60, anchor=tk.E)
                elif col == "Signal":
                    self.analysis_tree.column(col, width=80, anchor=tk.CENTER)
                elif col == "Sentiment":
                    self.analysis_tree.column(col, width=80, anchor=tk.E)
                else:
                    self.analysis_tree.column(col, width=120, anchor=tk.W)

            # Scrollbar for analysis tree
            analysis_scrollbar = ttk.Scrollbar(
                results_frame, orient=tk.VERTICAL, command=self.analysis_tree.yview
            )
            self.analysis_tree.configure(yscrollcommand=analysis_scrollbar.set)

            # Pack analysis tree and scrollbar
            self.analysis_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            analysis_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # Details area
            details_frame = ttk.LabelFrame(self.analysis_tab, text="Detailed Analysis")
            details_frame.pack(fill=tk.X, padx=5, pady=5)

            self.analysis_details = scrolledtext.ScrolledText(
                details_frame, height=6, font=("Consolas", 9)
            )
            self.analysis_details.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            # Bind selection event
            self.analysis_tree.bind("<<TreeviewSelect>>", self.on_analysis_select)

        except Exception as e:
            print(f"Error creating market analysis tab: {e}")

    def create_trade_signals_tab(self):
        """Create trade signals tab."""
        try:
            self.signals_tab = ttk.Frame(self.notebook)
            self.notebook.add(self.signals_tab, text="Trade\nSignals")

            # Controls
            controls_frame = ttk.LabelFrame(self.signals_tab, text="Signal Controls")
            controls_frame.pack(fill=tk.X, padx=5, pady=5)

            button_frame = ttk.Frame(controls_frame)
            button_frame.pack(fill=tk.X, padx=5, pady=2)

            self.generate_signals_btn = ttk.Button(
                button_frame,
                text="Generate Signals",
                command=self.generate_trade_signals,
            )
            self.generate_signals_btn.pack(side=tk.LEFT)

            self.clear_signals_btn = ttk.Button(
                button_frame, text="Clear Signals", command=self.clear_signals
            )
            self.clear_signals_btn.pack(side=tk.LEFT, padx=(5, 0))

            # Filter frame
            filter_frame = ttk.Frame(controls_frame)
            filter_frame.pack(fill=tk.X, padx=5, pady=2)

            ttk.Label(filter_frame, text="Filter by:").pack(side=tk.LEFT)

            self.signal_filter = ttk.Combobox(
                filter_frame,
                values=["All", "BUY", "SELL", "HOLD", "High Confidence (>70%)"],
                state="readonly",
                width=20,
            )
            self.signal_filter.set("All")
            self.signal_filter.pack(side=tk.LEFT, padx=(5, 0))
            self.signal_filter.bind("<<ComboboxSelected>>", self.filter_signals)

            # Signals tree
            signals_frame = ttk.LabelFrame(self.signals_tab, text="Trade Signals")
            signals_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            signal_columns = (
                "Symbol",
                "Signal",
                "Strength",
                "Confidence",
                "Price Target",
                "Stop Loss",
                "Time Horizon",
                "Generated",
            )
            self.signals_tree = ttk.Treeview(
                signals_frame, columns=signal_columns, show="headings", height=12
            )

            # Setup signal columns
            for col in signal_columns:
                self.signals_tree.heading(col, text=col)
                if col == "Symbol":
                    self.signals_tree.column(col, width=80, anchor=tk.W)
                elif col in ["Signal", "Strength"]:
                    self.signals_tree.column(col, width=80, anchor=tk.CENTER)
                elif col == "Confidence":
                    self.signals_tree.column(col, width=80, anchor=tk.E)
                elif col in ["Price Target", "Stop Loss"]:
                    self.signals_tree.column(col, width=100, anchor=tk.E)
                elif col == "Time Horizon":
                    self.signals_tree.column(col, width=90, anchor=tk.CENTER)
                else:
                    self.signals_tree.column(col, width=120, anchor=tk.W)

            # Scrollbar for signals tree
            signals_scrollbar = ttk.Scrollbar(
                signals_frame, orient=tk.VERTICAL, command=self.signals_tree.yview
            )
            self.signals_tree.configure(yscrollcommand=signals_scrollbar.set)

            # Pack signals tree and scrollbar
            self.signals_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            signals_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # Signal details
            signal_details_frame = ttk.LabelFrame(
                self.signals_tab, text="Signal Reasoning"
            )
            signal_details_frame.pack(fill=tk.X, padx=5, pady=5)

            self.signal_details = scrolledtext.ScrolledText(
                signal_details_frame, height=5, font=("Consolas", 9)
            )
            self.signal_details.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            # Bind selection event
            self.signals_tree.bind("<<TreeviewSelect>>", self.on_signal_select)

        except Exception as e:
            print(f"Error creating trade signals tab: {e}")

    def create_research_reports_tab(self):
        """Create research reports tab."""
        try:
            self.reports_tab = ttk.Frame(self.notebook)
            self.notebook.add(self.reports_tab, text="Research\nReports")

            # Controls
            controls_frame = ttk.LabelFrame(self.reports_tab, text="Report Generation")
            controls_frame.pack(fill=tk.X, padx=5, pady=5)

            # Report type selection
            type_frame = ttk.Frame(controls_frame)
            type_frame.pack(fill=tk.X, padx=5, pady=2)

            ttk.Label(type_frame, text="Report Type:").pack(side=tk.LEFT)
            self.report_type = ttk.Combobox(
                type_frame,
                values=["Market Overview", "Symbol Analysis", "Portfolio Analysis"],
                state="readonly",
                width=20,
            )
            self.report_type.set("Market Overview")
            self.report_type.pack(side=tk.LEFT, padx=(5, 0))

            # Generate button
            self.generate_report_btn = ttk.Button(
                type_frame, text="Generate Report", command=self.generate_report
            )
            self.generate_report_btn.pack(side=tk.LEFT, padx=(10, 0))

            self.save_report_btn = ttk.Button(
                type_frame,
                text="Save Report",
                command=self.save_report,
                state="disabled",
            )
            self.save_report_btn.pack(side=tk.LEFT, padx=(5, 0))

            # Report display
            report_frame = ttk.LabelFrame(self.reports_tab, text="Report Content")
            report_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            self.report_display = scrolledtext.ScrolledText(
                report_frame, font=("Consolas", 9), wrap=tk.WORD
            )
            self.report_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        except Exception as e:
            print(f"Error creating research reports tab: {e}")

    def create_settings_tab(self):
        """Create settings and configuration tab."""
        try:
            self.settings_tab = ttk.Frame(self.notebook)
            self.notebook.add(self.settings_tab, text="Settings")

            # LLM Configuration
            llm_frame = ttk.LabelFrame(self.settings_tab, text="LLM Configuration")
            llm_frame.pack(fill=tk.X, padx=5, pady=5)

            # API Key
            api_frame = ttk.Frame(llm_frame)
            api_frame.pack(fill=tk.X, padx=5, pady=2)

            ttk.Label(api_frame, text="OpenAI API Key:").pack(side=tk.LEFT)
            self.api_key_entry = ttk.Entry(
                api_frame, width=50, show="*", font=("Consolas", 9)
            )
            self.api_key_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)

            # Model selection
            model_frame = ttk.Frame(llm_frame)
            model_frame.pack(fill=tk.X, padx=5, pady=2)

            ttk.Label(model_frame, text="Model:").pack(side=tk.LEFT)
            self.model_combo = ttk.Combobox(
                model_frame,
                values=self.fetch_openai_models(),
                state="readonly",
                width=25,
            )
            # Set default to first gpt-4 model or first available
            default_models = self.available_models
            gpt4_models = [m for m in default_models if "gpt-4" in m]
            if gpt4_models:
                self.model_combo.set(gpt4_models[0])
            elif default_models:
                self.model_combo.set(default_models[0])
            else:
                self.model_combo.set("gpt-4")
            self.model_combo.pack(side=tk.LEFT, padx=(5, 0))

            # Refresh models button
            self.refresh_models_btn = ttk.Button(
                model_frame,
                text="🔄",
                width=3,
                command=self.refresh_models,
                style="Accent.TButton",
            )
            self.refresh_models_btn.pack(side=tk.LEFT, padx=(5, 0))

            # Apply settings button
            self.apply_settings_btn = ttk.Button(
                llm_frame, text="Apply Settings", command=self.apply_settings
            )
            self.apply_settings_btn.pack(pady=5)
        except Exception as e:
            print(f"Error creating settings tab: {e}")

    def refresh_models(self):
        """Refresh the OpenAI models list."""
        try:
            self.models_loaded = False  # Force refresh
            self.status_label.config(text="Refreshing models...")
            self.refresh_models_btn.config(state="disabled")

            # Run in background thread to avoid blocking UI
            def fetch_and_update():
                try:
                    self.update_model_combobox()
                    # Update status on main thread
                    self.parent.after(
                        0,
                        lambda: self.status_label.config(
                            text=f"Models updated - {len(self.available_models)} available"
                        ),
                    )
                except Exception as e:
                    self.parent.after(
                        0,
                        lambda: self.status_label.config(
                            text=f"Model refresh failed: {str(e)}"
                        ),
                    )
                finally:
                    self.parent.after(
                        0, lambda: self.refresh_models_btn.config(state="normal")
                    )

            threading.Thread(target=fetch_and_update, daemon=True).start()

        except Exception as e:
            self.status_label.config(text=f"Error refreshing models: {e}")
            self.refresh_models_btn.config(state="normal")

            # Analysis Settings
            analysis_frame = ttk.LabelFrame(self.settings_tab, text="Analysis Settings")
            analysis_frame.pack(fill=tk.X, padx=5, pady=5)

            # News settings
            news_frame = ttk.Frame(analysis_frame)
            news_frame.pack(fill=tk.X, padx=5, pady=2)

            self.include_news = tk.BooleanVar(value=True)
            ttk.Checkbutton(
                news_frame, text="Include News Analysis", variable=self.include_news
            ).pack(side=tk.LEFT)

            # Cache settings
            cache_frame = ttk.Frame(analysis_frame)
            cache_frame.pack(fill=tk.X, padx=5, pady=2)

            ttk.Label(cache_frame, text="Cache Duration (minutes):").pack(side=tk.LEFT)
            self.cache_duration = ttk.Spinbox(
                cache_frame, from_=1, to=60, width=10, value=10
            )
            self.cache_duration.pack(side=tk.LEFT, padx=(5, 0))

            # Engine Status
            status_frame = ttk.LabelFrame(self.settings_tab, text="Engine Status")
            status_frame.pack(fill=tk.X, padx=5, pady=5)

            self.status_text = scrolledtext.ScrolledText(
                status_frame, height=8, font=("Consolas", 9)
            )
            self.status_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            # Update status button
            self.update_status_btn = ttk.Button(
                status_frame, text="Update Status", command=self.update_engine_status
            )
            self.update_status_btn.pack(pady=2)

            # Initialize status
            self.update_engine_status()

        except Exception as e:
            print(f"Error creating settings tab: {e}")

    def run_market_analysis(self):
        """Run market analysis in background thread."""
        try:
            if not self.engine:
                messagebox.showerror("Error", "Research engine not available")
                return

            symbols_text = self.symbol_entry.get().strip()
            if not symbols_text:
                messagebox.showwarning("Warning", "Please enter symbols to analyze")
                return

            symbols = [s.strip().upper() for s in symbols_text.split(",") if s.strip()]
            self.current_symbols = symbols

            # Disable button and show progress
            self.analyze_btn.config(state="disabled", text="Analyzing...")
            self.status_label.config(text="Running market analysis...")

            # Run analysis in background
            self.analysis_thread = threading.Thread(
                target=self._run_analysis_worker, args=(symbols,), daemon=True
            )
            self.analysis_thread.start()

        except Exception as e:
            print(f"Error starting market analysis: {e}")
            messagebox.showerror("Error", f"Failed to start analysis: {str(e)}")
            self.analyze_btn.config(state="normal", text="Analyze Market")

    def _run_analysis_worker(self, symbols: List[str]):
        """Worker thread for market analysis."""
        try:
            # Run analysis
            analysis = self.engine.analyze_market(
                symbols, include_news=self.include_news.get()
            )

            # Update GUI in main thread
            self.parent.after(0, self._update_analysis_results, analysis)

        except Exception as e:
            print(f"Error in analysis worker: {e}")
            self.parent.after(0, self._analysis_error, str(e))

    def _update_analysis_results(self, analysis: Dict[str, Any]):
        """Update analysis results in GUI."""
        try:
            # Clear existing results
            for item in self.analysis_tree.get_children():
                self.analysis_tree.delete(item)

            # Add new results
            for signal_data in analysis.get("trade_signals", []):
                signal = TradeSignal(**signal_data)

                # Find corresponding market data
                market_data = None
                for data in analysis.get("market_data", []):
                    if data["symbol"] == signal.symbol:
                        market_data = data
                        break

                if market_data:
                    # Color code based on signal
                    tags = []
                    if signal.signal_type == "BUY":
                        tags.append("buy_signal")
                    elif signal.signal_type == "SELL":
                        tags.append("sell_signal")

                    self.analysis_tree.insert(
                        "",
                        tk.END,
                        values=(
                            signal.symbol,
                            f"${market_data.get('current_price', 0):.4f}",
                            f"{market_data.get('price_change_pct_24h', 0):+.2f}%",
                            f"{market_data.get('rsi', 0):.1f}"
                            if market_data.get("rsi")
                            else "N/A",
                            signal.signal_type,
                            f"{analysis.get('market_sentiment', 0):+.2f}",
                            signal.generated_at.strftime("%H:%M:%S"),
                        ),
                        tags=tags,
                    )

            # Configure tags
            self.analysis_tree.tag_configure("buy_signal", foreground="green")
            self.analysis_tree.tag_configure("sell_signal", foreground="red")

            # Update status
            signal_count = len(analysis.get("trade_signals", []))
            self.status_label.config(
                text=f"Analysis complete: {signal_count} signals generated"
            )

        except Exception as e:
            print(f"Error updating analysis results: {e}")
        finally:
            # Re-enable button
            self.analyze_btn.config(state="normal", text="Analyze Market")

    def _analysis_error(self, error_msg: str):
        """Handle analysis error."""
        try:
            self.status_label.config(text=f"Analysis failed: {error_msg}")
            messagebox.showerror(
                "Analysis Error", f"Failed to run analysis:\n{error_msg}"
            )
        finally:
            self.analyze_btn.config(state="normal", text="Analyze Market")

    def on_analysis_select(self, event):
        """Handle analysis tree selection."""
        try:
            selection = self.analysis_tree.selection()
            if not selection:
                return

            item = self.analysis_tree.item(selection[0])
            values = item["values"]

            if values:
                symbol = values[0]
                # Get detailed analysis for symbol
                details = f"Detailed Analysis for {symbol}\n"
                details += "=" * 40 + "\n\n"
                details += f"Current Price: {values[1]}\n"
                details += f"24h Change: {values[2]}\n"
                details += f"RSI: {values[3]}\n"
                details += f"Signal: {values[4]}\n"
                details += f"Sentiment: {values[5]}\n"
                details += f"Last Updated: {values[6]}\n\n"
                details += "Technical Analysis:\n"
                details += "- Price above/below key moving averages\n"
                details += "- RSI indicating overbought/oversold conditions\n"
                details += "- Volume patterns and momentum\n\n"
                details += "Recommendation:\n"
                details += f"Based on current analysis, the signal for {symbol} is {values[4]}.\n"
                details += "Please consider risk management and position sizing."

                self.analysis_details.delete(1.0, tk.END)
                self.analysis_details.insert(1.0, details)

        except Exception as e:
            print(f"Error handling analysis selection: {e}")

    def generate_trade_signals(self):
        """Generate trade signals."""
        try:
            if not self.engine:
                messagebox.showerror("Error", "Research engine not available")
                return

            if not self.current_symbols:
                symbols_text = self.symbol_entry.get().strip()
                if not symbols_text:
                    messagebox.showwarning(
                        "Warning", "Please enter symbols or run market analysis first"
                    )
                    return
                symbols = [
                    s.strip().upper() for s in symbols_text.split(",") if s.strip()
                ]
            else:
                symbols = self.current_symbols

            # Disable button
            self.generate_signals_btn.config(state="disabled", text="Generating...")
            self.status_label.config(text="Generating trade signals...")

            # Generate signals in background
            threading.Thread(
                target=self._generate_signals_worker, args=(symbols,), daemon=True
            ).start()

        except Exception as e:
            print(f"Error generating signals: {e}")
            messagebox.showerror("Error", f"Failed to generate signals: {str(e)}")
            self.generate_signals_btn.config(state="normal", text="Generate Signals")

    def _generate_signals_worker(self, symbols: List[str]):
        """Worker thread for generating signals."""
        try:
            signals = self.engine.get_trade_signals(symbols, force_refresh=True)
            self.parent.after(0, self._update_signals_display, signals)

        except Exception as e:
            print(f"Error in signals worker: {e}")
            self.parent.after(0, self._signals_error, str(e))

    def _update_signals_display(self, signals: List[TradeSignal]):
        """Update signals display."""
        try:
            # Clear existing signals
            for item in self.signals_tree.get_children():
                self.signals_tree.delete(item)

            # Add new signals
            for signal in signals:
                # Color code based on signal type and confidence
                tags = []
                if signal.signal_type == "BUY":
                    tags.append("buy_signal")
                elif signal.signal_type == "SELL":
                    tags.append("sell_signal")

                if signal.confidence >= 70:
                    tags.append("high_confidence")

                price_target = (
                    f"${signal.price_target:.4f}" if signal.price_target else "N/A"
                )
                stop_loss = f"${signal.stop_loss:.4f}" if signal.stop_loss else "N/A"

                self.signals_tree.insert(
                    "",
                    tk.END,
                    values=(
                        signal.symbol,
                        signal.signal_type,
                        signal.strength.value.replace("_", " ").title(),
                        f"{signal.confidence:.1f}%",
                        price_target,
                        stop_loss,
                        signal.time_horizon,
                        signal.generated_at.strftime("%H:%M:%S"),
                    ),
                    tags=tags,
                )

            # Configure tags
            self.signals_tree.tag_configure("buy_signal", foreground="green")
            self.signals_tree.tag_configure("sell_signal", foreground="red")
            self.signals_tree.tag_configure(
                "high_confidence", font=("TkDefaultFont", 9, "bold")
            )

            self.status_label.config(text=f"Generated {len(signals)} trade signals")

        except Exception as e:
            print(f"Error updating signals display: {e}")
        finally:
            self.generate_signals_btn.config(state="normal", text="Generate Signals")

    def _signals_error(self, error_msg: str):
        """Handle signals generation error."""
        try:
            self.status_label.config(text=f"Signal generation failed: {error_msg}")
            messagebox.showerror(
                "Signals Error", f"Failed to generate signals:\n{error_msg}"
            )
        finally:
            self.generate_signals_btn.config(state="normal", text="Generate Signals")

    def on_signal_select(self, event):
        """Handle signal tree selection."""
        try:
            selection = self.signals_tree.selection()
            if not selection:
                return

            item = self.signals_tree.item(selection[0])
            values = item["values"]

            if values and self.engine:
                symbol = values[0]
                # Get signal reasoning (mock for now)
                reasoning = f"Trade Signal Analysis for {symbol}\n"
                reasoning += "=" * 40 + "\n\n"
                reasoning += f"Signal: {values[1]} ({values[2]})\n"
                reasoning += f"Confidence: {values[3]}\n"
                reasoning += f"Price Target: {values[4]}\n"
                reasoning += f"Stop Loss: {values[5]}\n"
                reasoning += f"Time Horizon: {values[6]}\n\n"
                reasoning += "Reasoning:\n"
                reasoning += f"The LLM analysis for {symbol} indicates a {values[1]} signal based on:\n\n"
                reasoning += "• Technical indicators showing momentum\n"
                reasoning += "• Market sentiment analysis from recent news\n"
                reasoning += "• Price action and volume patterns\n"
                reasoning += "• Risk/reward ratio considerations\n\n"
                reasoning += "Risk Management:\n"
                reasoning += "• Use proper position sizing\n"
                reasoning += "• Set stop-loss orders as indicated\n"
                reasoning += "• Monitor for signal invalidation\n"
                reasoning += "• Consider market conditions"

                self.signal_details.delete(1.0, tk.END)
                self.signal_details.insert(1.0, reasoning)

        except Exception as e:
            print(f"Error handling signal selection: {e}")

    def generate_report(self):
        """Generate research report."""
        try:
            if not self.engine:
                messagebox.showerror("Error", "Research engine not available")
                return

            report_type = self.report_type.get()

            # Map GUI selection to engine types
            type_mapping = {
                "Market Overview": "market_overview",
                "Symbol Analysis": "symbol_analysis",
                "Portfolio Analysis": "portfolio_analysis",
            }

            engine_type = type_mapping.get(report_type, "market_overview")

            # Get symbols for report
            symbols = self.current_symbols or ["BTCUSDT", "ETHUSDT", "ADAUSDT"]

            # Disable button
            self.generate_report_btn.config(state="disabled", text="Generating...")
            self.status_label.config(text=f"Generating {report_type} report...")

            # Generate report in background
            threading.Thread(
                target=self._generate_report_worker,
                args=(engine_type, symbols),
                daemon=True,
            ).start()

        except Exception as e:
            print(f"Error generating report: {e}")
            messagebox.showerror("Error", f"Failed to generate report: {str(e)}")

    def _generate_report_worker(self, report_type: str, symbols: List[str]):
        """Worker thread for report generation."""
        try:
            report = self.engine.generate_research_report(report_type, symbols)
            self.parent.after(0, self._update_report_display, report)

        except Exception as e:
            print(f"Error in report worker: {e}")
            self.parent.after(0, self._report_error, str(e))

    def _update_report_display(self, report: str):
        """Update report display."""
        try:
            self.report_display.delete(1.0, tk.END)
            self.report_display.insert(1.0, report)
            self.save_report_btn.config(state="normal")
            self.status_label.config(text="Report generated successfully")

        except Exception as e:
            print(f"Error updating report display: {e}")
        finally:
            self.generate_report_btn.config(state="normal", text="Generate Report")

    def _report_error(self, error_msg: str):
        """Handle report generation error."""
        try:
            self.status_label.config(text=f"Report generation failed: {error_msg}")
            messagebox.showerror(
                "Report Error", f"Failed to generate report:\n{error_msg}"
            )
        finally:
            self.generate_report_btn.config(state="normal", text="Generate Report")

    def save_report(self):
        """Save research report to file."""
        try:
            from tkinter import filedialog

            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[
                    ("Text files", "*.txt"),
                    ("Markdown files", "*.md"),
                    ("All files", "*.*"),
                ],
                title="Save Research Report",
            )

            if file_path:
                content = self.report_display.get(1.0, tk.END)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

                messagebox.showinfo("Success", f"Report saved to: {file_path}")

        except Exception as e:
            print(f"Error saving report: {e}")
            messagebox.showerror("Error", f"Failed to save report: {str(e)}")

    def clear_analysis(self):
        """Clear analysis results."""
        try:
            for item in self.analysis_tree.get_children():
                self.analysis_tree.delete(item)
            self.analysis_details.delete(1.0, tk.END)
            self.status_label.config(text="Analysis cleared")

        except Exception as e:
            print(f"Error clearing analysis: {e}")

    def clear_signals(self):
        """Clear trade signals."""
        try:
            for item in self.signals_tree.get_children():
                self.signals_tree.delete(item)
            self.signal_details.delete(1.0, tk.END)
            self.status_label.config(text="Signals cleared")

        except Exception as e:
            print(f"Error clearing signals: {e}")

    def filter_signals(self, event=None):
        """Filter signals based on selected criteria."""
        try:
            # This would filter the signals tree based on selected filter
            # Implementation would depend on storing signal data separately
            filter_value = self.signal_filter.get()
            self.status_label.config(text=f"Filter applied: {filter_value}")

        except Exception as e:
            print(f"Error filtering signals: {e}")

    def apply_settings(self):
        """Apply LLM and analysis settings."""
        try:
            api_key = self.api_key_entry.get().strip()
            model = self.model_combo.get()

            if not api_key:
                messagebox.showwarning("Warning", "Please enter OpenAI API key")
                return

            # Update engine configuration
            if self.engine:
                self.engine.llm_provider.api_key = api_key
                self.engine.llm_provider.model = model
                self.engine.llm_provider._setup_client()

                messagebox.showinfo("Success", "Settings applied successfully")
                self.update_engine_status()
            else:
                messagebox.showerror("Error", "Research engine not available")

        except Exception as e:
            print(f"Error applying settings: {e}")
            messagebox.showerror("Error", f"Failed to apply settings: {str(e)}")

    def update_engine_status(self):
        """Update engine status display."""
        try:
            if not self.engine:
                status = "Research Engine: Not Available\n"
                status += "Please check installation and dependencies."
            else:
                summary = self.engine.get_analysis_summary()
                status = "Research Engine Status\n"
                status += "=" * 30 + "\n\n"
                status += f"LLM Provider Available: {summary.get('llm_provider_available', False)}\n"
                status += f"Cache Entries: {summary.get('cache_entries', 0)}\n"
                status += (
                    f"Signal Cache Entries: {summary.get('signal_cache_entries', 0)}\n"
                )
                status += f"Background Analysis: {summary.get('background_analysis_running', False)}\n\n"

                if summary.get("last_analyses"):
                    status += "Recent Analyses:\n"
                    for key, timestamp in summary.get("last_analyses", {}).items():
                        status += f"  {key}: {timestamp}\n"
                else:
                    status += "No recent analyses\n"

                if summary.get("error"):
                    status += f"\nError: {summary['error']}"

            self.status_text.delete(1.0, tk.END)
            self.status_text.insert(1.0, status)

        except Exception as e:
            print(f"Error updating engine status: {e}")

    def toggle_auto_refresh(self):
        """Toggle auto-refresh for market analysis."""
        try:
            if self.auto_refresh.get():
                # Start auto-refresh
                self.running = True
                self.refresh_thread = threading.Thread(
                    target=self._auto_refresh_worker, daemon=True
                )
                self.refresh_thread.start()
                self.status_label.config(text="Auto-refresh enabled")
            else:
                # Stop auto-refresh
                self.running = False
                self.status_label.config(text="Auto-refresh disabled")

        except Exception as e:
            print(f"Error toggling auto-refresh: {e}")

    def _auto_refresh_worker(self):
        """Auto-refresh worker thread."""
        try:
            while self.running and self.auto_refresh.get():
                if self.current_symbols:
                    # Run analysis
                    analysis = self.engine.analyze_market(
                        self.current_symbols, include_news=self.include_news.get()
                    )

                    # Update GUI
                    self.parent.after(0, self._update_analysis_results, analysis)

                # Wait for next refresh
                interval_minutes = int(self.refresh_interval.get())
                time.sleep(interval_minutes * 60)

        except Exception as e:
            print(f"Error in auto-refresh worker: {e}")
        finally:
            self.running = False


# Integration function for main application
def create_research_engine_tab(parent, config: Dict = None):
    """Create research engine tab for main application."""
    try:
        research_gui = ResearchEngineGUI(parent, config)
        return research_gui.research_frame

    except Exception as e:
        print(f"Error creating research engine tab: {e}")
        # Return placeholder frame
        placeholder = ttk.Frame(parent)
        ttk.Label(
            placeholder,
            text="LLM Research Engine not available",
            font=("TkDefaultFont", 12),
        ).pack(expand=True)
        return placeholder


if __name__ == "__main__":
    # Test the GUI
    root = tk.Tk()
    root.title("LLM Research Engine - Test")
    root.geometry("1200x800")

    config = {
        "llm": {"api_key": "", "model": "gpt-4"}  # Add your API key here for testing
    }

    research_tab = create_research_engine_tab(root, config)
    research_tab.pack(fill=tk.BOTH, expand=True)

    root.mainloop()
