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

import ui_table
import ui_theme
import ui_tokens

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

        # Background threads
        self.refresh_thread = None
        self.analysis_thread = None
        self.running = False

        self.setup_gui()

    def setup_gui(self):
        """Setup the research engine GUI."""
        try:
            # Create main research frame
            self.research_frame = ttk.Frame(self.parent)
            self.research_frame.pack(fill=tk.BOTH, expand=True)

            if not RESEARCH_ENGINE_AVAILABLE:
                # Show message about unavailable research engine
                ttk.Label(
                    self.research_frame,
                    text="LLM Research Engine Dependencies Missing\n\nRequired modules:\n- OpenAI Python library\n- SQLAlchemy (optional)\n\nInstall with: pip install openai sqlalchemy",
                    font=ui_tokens.font("body"),
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

            # Status bar
            self.status_bar = ttk.Frame(self.research_frame)
            self.status_bar.pack(fill=tk.X, pady=(5, 0))

            self.status_label = ttk.Label(self.status_bar, text="Ready")
            self.status_label.pack(side=tk.LEFT)

            self.engine_status = ttk.Label(
                self.status_bar,
                text="Engine: " + ("Available" if self.engine else "Not Available"),
                style="Good.TLabel" if self.engine else "Bad.TLabel",
            )
            self.engine_status.pack(side=tk.RIGHT)

        except Exception as e:
            print(f"Error setting up research GUI: {e}")
            # Show error in the GUI
            try:
                ttk.Label(
                    self.research_frame,
                    text=f"LLM Research GUI Error\n\n{str(e)}\n\nCheck console for details.",
                    font=ui_tokens.font("body"),
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
            self.symbol_entry = ttk.Entry(
                symbol_frame, width=50, font=ui_tokens.mono("small")
            )
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

            # Analysis results table (ui_table: fitted columns, its own scrollbars)
            columns = (
                "Symbol",
                "Price",
                "Change %",
                "RSI",
                "Signal",
                "Sentiment",
                "Last Updated",
            )
            self.analysis_table = ui_table.DataTable(
                results_frame,
                columns,
                key="llm_research.analysis_results",
                numeric=("Price", "Change %", "RSI", "Sentiment"),
                empty_text="No results yet",
            )
            self.analysis_table.pack(fill="both", expand=True)
            self.analysis_tree = self.analysis_table.tree

            # Details area
            details_frame = ttk.LabelFrame(self.analysis_tab, text="Detailed Analysis")
            details_frame.pack(fill=tk.X, padx=5, pady=5)

            self.analysis_details = scrolledtext.ScrolledText(
                details_frame, height=6, font=ui_tokens.mono("small")
            )
            self.analysis_details.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            ui_table.scroll_when_needed(self.analysis_details)

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

            # Signals table, straight in the tab: a "Trade Signals" title round it
            # would only repeat the tab's name
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
            self.signals_table = ui_table.DataTable(
                self.signals_tab,
                signal_columns,
                key="llm_research.trade_signals",
                numeric=("Confidence", "Price Target", "Stop Loss"),
                empty_text="No signals yet",
            )
            self.signals_table.pack(fill="both", expand=True)
            self.signals_tree = self.signals_table.tree

            # Signal details
            signal_details_frame = ttk.LabelFrame(
                self.signals_tab, text="Signal Reasoning"
            )
            signal_details_frame.pack(fill=tk.X, padx=5, pady=5)

            self.signal_details = scrolledtext.ScrolledText(
                signal_details_frame, height=5, font=ui_tokens.mono("small")
            )
            self.signal_details.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            ui_table.scroll_when_needed(self.signal_details)

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
                report_frame, font=ui_tokens.mono("small"), wrap=tk.WORD
            )
            self.report_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            ui_table.scroll_when_needed(self.report_display)

        except Exception as e:
            print(f"Error creating research reports tab: {e}")

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
            analysis = self.engine.analyze_market(symbols, include_news=False)

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
                            (
                                f"{market_data.get('rsi', 0):.1f}"
                                if market_data.get("rsi")
                                else "N/A"
                            ),
                            signal.signal_type,
                            f"{analysis.get('market_sentiment', 0):+.2f}",
                            signal.generated_at.strftime("%H:%M:%S"),
                        ),
                        tags=tags,
                    )

            # Configure tags
            self.analysis_tree.tag_configure(
                "buy_signal", foreground=ui_tokens.STATUS["good"]
            )
            self.analysis_tree.tag_configure(
                "sell_signal", foreground=ui_tokens.STATUS["short"]
            )

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
            self.signals_tree.tag_configure(
                "buy_signal", foreground=ui_tokens.STATUS["good"]
            )
            self.signals_tree.tag_configure(
                "sell_signal", foreground=ui_tokens.STATUS["short"]
            )
            self.signals_tree.tag_configure(
                "high_confidence", font=ui_tokens.font("small", "bold")
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
                        self.current_symbols, include_news=False
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
            font=ui_tokens.font("title"),
        ).pack(expand=True)
        return placeholder
