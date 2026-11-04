"""The hub's Long-term Holdings tab (owner, 2026-11-04).

Manual HODL positions, kept in holdings.db (long_term_holdings) and tracked apart
from the trading account: the account's Value, Buying Power and % in Trade do not
include them, and nothing here reads or changes the paper or live account. Four
sub-tabs:

* Holdings: a toolbar (Add Holding, Edit, Delete, Update Prices, Export CSV,
  Refresh and a search through every column) over the holdings, in the shared
  table (ui_table.DataTable), with each holding's share of the holdings' current
  value ("% of Holdings").
* Portfolio Overview: the holdings' totals beside the allocation, a pie of each
  holding's share of their current value. With no holdings, only "No holdings to
  display".
* Rebalancing: the holdings whose share is further from their target % than their
  rebalance threshold, worked out again whenever the holdings change, in the shared
  table; Export CSV and a search.
* Analytics, from holdings.db: each holding's unrealised P&L % (its current price
  against its average cost) and the prices recorded with Update Prices, as the
  change since each coin's first recorded price. With no holdings, "No data yet".

Add Holding and Edit open HoldingDialog: the coin from the hub's coins (Settings),
the exchange from the exchanges in Settings, primary first (or typed, e.g. a
wallet), and the coin's market on that exchange in the exchange layer's format
(``BTC-USD`` on Coinbase, ``BTCUSDT`` on Binance). holdings.db keeps the coin as
before (``BTC``); nothing here changes what it stores.
"""

import csv
import math
import tkinter as tk
from collections import Counter
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

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
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    from matplotlib.ticker import FuncFormatter

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

SUB_TABS = ("Holdings", "Portfolio Overview", "Rebalancing", "Analytics")

# ---- the holdings table ----

HOLDINGS_COLUMNS = (
    "symbol",
    "quantity",
    "avg_cost",
    "current_price",
    "total_cost",
    "current_value",
    "pnl",
    "pnl_pct",
    "share",
    "target_pct",
    "exchange",
)
HOLDINGS_HEADINGS = {
    "symbol": "Coin",
    "quantity": "Quantity",
    "avg_cost": "Avg Cost",
    "current_price": "Current Price",
    "total_cost": "Total Cost",
    "current_value": "Current Value",
    "pnl": "P&L",
    "pnl_pct": "P&L %",
    # the share of the holdings' own current value, not of the trading account
    "share": "% of Holdings",
    "target_pct": "Target %",
    "exchange": "Exchange",
}
HOLDINGS_NUMERIC = tuple(c for c in HOLDINGS_COLUMNS if c not in ("symbol", "exchange"))
NO_HOLDINGS = "No holdings yet"
NO_HOLDINGS_MATCH = "No holdings match the search"

# ---- the rebalancing table ----

REBALANCE_COLUMNS = (
    "symbol",
    "action",
    "current_pct",
    "target_pct",
    "deviation",
    "amount_diff",
)
REBALANCE_HEADINGS = {
    "symbol": "Coin",
    "action": "Action",
    "current_pct": "% of Holdings",
    "target_pct": "Target %",
    "deviation": "Deviation %",
    "amount_diff": "Amount",
}
REBALANCE_NUMERIC = ("current_pct", "target_pct", "deviation", "amount_diff")
NO_TARGETS = "No holding has a target %"
IN_BALANCE = "Every holding is within its rebalance threshold of its target %"
NO_SUGGESTIONS_MATCH = "No suggestions match the search"

# ---- Portfolio Overview and Analytics ----

NO_OVERVIEW = "No holdings to display"
NO_ANALYTICS = "No data yet"
NO_PRICES = "No holding has a current price yet"
NO_CHARTS = "Charts need matplotlib"
SUMMARY_ROWS = (
    ("Holdings", "holdings_count"),
    ("Total Cost", "total_cost"),
    ("Current Value", "total_value"),
    ("Total P&L", "total_pnl"),
    ("Total P&L %", "total_pnl_pct"),
)
PNL_TITLE = "Unrealised P&L %"
LEVEL_LABELS = 8  # past this many coins, the P&L chart's coin names stand upright
PRICES_TITLE = "Recorded prices, % change"
ALLOCATION_TITLE = "Allocation, % of Holdings"


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _price(value: float) -> str:
    return "$" + f"{value:,.8f}".rstrip("0").rstrip(".")


def plain_number(value: Any) -> str:
    """A quantity or price as typed: no grouping, no trailing zeros."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:.8f}".rstrip("0").rstrip(".") or "0"


def signed_money(value: float, money: Callable[[float], str] = _money) -> str:
    return ("-" if value < 0 else "+") + money(abs(value))


def _number(text: str, default: float = 0.0) -> float:
    """A number typed in a field (blank: ``default``); ValueError when it is not
    a finite number."""
    text = str(text).replace(",", "").strip()
    if not text:
        return default
    number = float(text)
    if not math.isfinite(number):
        raise ValueError(text)
    return number


def _show(widget: tk.Widget, shown: bool) -> None:
    """Pack ``widget`` to fill its parent, or take it out."""
    if shown:
        if not widget.winfo_manager():
            widget.pack(fill="both", expand=True)
    elif widget.winfo_manager():
        widget.pack_forget()


# ---- symbols, through the exchange layer ----


class ExchangeSymbols:
    """The exchanges in Settings, primary first, and a coin's market on each, from
    the exchange layer (``pt_multi_exchange.market_exchanges``: public market data,
    no credentials). Working out a market symbol sends no request."""

    def __init__(self, layer: Optional[Callable[[], Any]] = None):
        self._layer = layer

    def _manager(self):
        if self._layer is not None:
            return self._layer()
        from pt_multi_exchange import market_exchanges

        return market_exchanges()

    def exchanges(self) -> List[str]:
        """The connected exchanges' ids, primary first, then the Settings order."""
        try:
            return list(self._manager().exchange_manager.exchange_names())
        except Exception:
            return []

    def market(self, coin: str, exchange: str = "") -> Tuple[str, str]:
        """``coin``'s market and the id of the exchange it is on: ``exchange`` (an id
        or the name ``exchange_name`` gives it) when it is one of the exchanges in
        Settings, otherwise the first of them, the primary. With none connected, the
        connectors' own form (``BTC-USD``) and no exchange."""
        from pt_exchange_abstraction import ExchangeType, dollar_symbol, exchange_id

        symbol = dollar_symbol(coin)
        try:
            em = self._manager().exchange_manager
            names = list(em.exchange_names())
        except Exception:
            return symbol, ""
        wanted = exchange_id(exchange) if str(exchange or "").strip() else ""
        chosen = wanted if wanted in names else (names[0] if names else "")
        if not chosen:
            return symbol, ""
        try:
            return em.exchanges[ExchangeType(chosen)].market_symbol(symbol), chosen
        except Exception:
            return symbol, chosen


class HoldingsManagementGUI:
    """The Long-term Holdings tab's four sub-tabs; see the module docstring.

    ``coins`` gives the hub's coins (Settings) when a holding is added or edited;
    ``manager`` is the HoldingsManager (None: the shared one, on holdings.db in the
    user data folder); ``symbols`` an ExchangeSymbols; ``money`` and ``price``
    format amounts and prices."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        coins: Callable[[], Sequence[str]] = lambda: (),
        manager: Optional["HoldingsManager"] = None,
        symbols: Optional[ExchangeSymbols] = None,
        money: Callable[[float], str] = _money,
        price: Callable[[float], str] = _price,
    ):
        if not isinstance(parent, tk.Misc):
            # a stand-in parent (a mock) has no end to its masters: the search
            # box's Tk variable would look for its root for ever
            raise TypeError(f"the parent must be a Tk widget, not {type(parent)}")
        self.parent = parent
        self._coins = coins
        self.symbols = symbols if symbols is not None else ExchangeSymbols()
        self._money, self._price = money, price
        self.holdings_manager = manager
        self.selected_holding: Optional["Holding"] = None
        self.dialog: Optional["HoldingDialog"] = None
        # what the Analytics charts show (tests): [(label, P&L %)], {coin: [% change]}
        self.analytics_pnl: List[Tuple[str, float]] = []
        self.analytics_prices: Dict[str, List[float]] = {}

        if self.holdings_manager is None and HOLDINGS_AVAILABLE:
            try:
                self.holdings_manager = get_holdings_manager()
            except Exception as e:
                print(f"Error initializing holdings manager: {e}")

        self.setup_ui()
        self.refresh_holdings_display()

    def setup_ui(self):
        """The four sub-tabs, in a notebook filling the parent."""
        self.main_frame = ttk.Frame(self.parent)
        self.main_frame.pack(fill="both", expand=True)

        # inside the hub's bottom panel this notebook draws no border of its own
        # (ui_table.borderless_inside): the panel's is the only one
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill="both", expand=True)

        self.holdings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.holdings_tab, text=SUB_TABS[0])
        self.setup_holdings_tab()

        self.portfolio_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.portfolio_tab, text=SUB_TABS[1])
        self.setup_portfolio_tab()

        self.rebalancing_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.rebalancing_tab, text=SUB_TABS[2])
        self.setup_rebalancing_tab()

        self.analytics_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.analytics_tab, text=SUB_TABS[3])
        self.setup_analytics_tab()

    # ---- the sub-tabs ----

    def _toolbar(self, tab: tk.Widget) -> ttk.Frame:
        gap = ui_tokens.SPACE["sm"]
        bar = ttk.Frame(tab)
        bar.pack(side="top", fill="x", padx=gap, pady=(gap, gap))
        return bar

    def setup_holdings_tab(self):
        """A toolbar over the holdings table."""
        gap = ui_tokens.SPACE["sm"]
        bar = self._toolbar(self.holdings_tab)
        for text, command in (
            ("Add Holding", self.add_holding_dialog),
            ("Edit", self.edit_holding_dialog),
            ("Delete", self.delete_holding),
            ("Update Prices", self.update_prices_dialog),
            ("Export CSV", self.export_holdings),
            ("Refresh", self.refresh_holdings_display),
        ):
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=(0, gap))
        self.holdings_search = ui_table.SearchBox(bar, self.show_holdings)
        self.search_var = self.holdings_search.var

        self.holdings_table = ui_table.DataTable(
            self.holdings_tab,
            HOLDINGS_COLUMNS,
            HOLDINGS_HEADINGS,
            key="holdings_management.holdings",
            numeric=HOLDINGS_NUMERIC,
            empty_text=NO_HOLDINGS,
            selectmode="browse",
        )
        self.holdings_table.pack(side="top", fill="both", expand=True)
        self.holdings_tree = self.holdings_table.tree
        status = ui_tokens.STATUS
        self.holdings_tree.tag_configure("profit", foreground=status["good"])
        self.holdings_tree.tag_configure("loss", foreground=status["bad"])
        self.holdings_tree.bind("<<TreeviewSelect>>", self.on_holding_select)

    def setup_portfolio_tab(self):
        """The totals beside the allocation chart; with no holdings, one message."""
        gap = ui_tokens.SPACE["sm"]
        tab = self.portfolio_tab
        self.overview_empty = ttk.Label(
            tab, text=NO_OVERVIEW, style="Muted.TLabel", anchor="center"
        )
        self.overview_body = ttk.Frame(tab)

        summary = ttk.Frame(self.overview_body)
        summary.pack(side="left", fill="y", padx=(ui_tokens.SPACE["lg"], gap), pady=gap)
        self.summary_labels: Dict[str, ttk.Label] = {}
        for i, (text, key) in enumerate(SUMMARY_ROWS):
            ttk.Label(summary, text=text).grid(row=i, column=0, sticky="w", pady=2)
            value = ttk.Label(summary, text="")
            value.grid(row=i, column=1, sticky="e", padx=(gap * 2, 0), pady=2)
            self.summary_labels[key] = value

        self.chart_area = ttk.Frame(self.overview_body)
        self.chart_area.pack(side="left", fill="both", expand=True)
        self.chart_note = ttk.Label(
            self.chart_area, text="", style="Muted.TLabel", anchor="center"
        )
        if MATPLOTLIB_AVAILABLE:
            # a small first size: the canvas takes the room it is given
            self.portfolio_fig = Figure(
                figsize=(4, 2.5), facecolor=ui_tokens.CHART["figure"]
            )
            self.portfolio_canvas = FigureCanvasTkAgg(
                self.portfolio_fig, self.chart_area
            )
            self.portfolio_widget = self.portfolio_canvas.get_tk_widget()

    def setup_rebalancing_tab(self):
        """A toolbar over the suggestions table."""
        gap = ui_tokens.SPACE["sm"]
        bar = self._toolbar(self.rebalancing_tab)
        ttk.Button(bar, text="Export CSV", command=self.export_suggestions).pack(
            side="left", padx=(0, gap)
        )
        self.suggestions_search = ui_table.SearchBox(bar, self.show_suggestions)

        self.suggestions_table = ui_table.DataTable(
            self.rebalancing_tab,
            REBALANCE_COLUMNS,
            REBALANCE_HEADINGS,
            key="holdings_management.rebalancing",
            numeric=REBALANCE_NUMERIC,
            empty_text=NO_HOLDINGS,
        )
        self.suggestions_table.pack(side="top", fill="both", expand=True)
        self.suggestions_tree = self.suggestions_table.tree
        status = ui_tokens.STATUS
        self.suggestions_tree.tag_configure("buy", foreground=status["good"])
        self.suggestions_tree.tag_configure("sell", foreground=status["warn"])

    def setup_analytics_tab(self):
        """The P&L and recorded-price charts; with nothing to chart, one message."""
        tab = self.analytics_tab
        self.analytics_empty = ttk.Label(
            tab, text=NO_ANALYTICS, style="Muted.TLabel", anchor="center"
        )
        if MATPLOTLIB_AVAILABLE:
            self.analytics_fig = Figure(
                figsize=(5, 2.5),
                facecolor=ui_tokens.CHART["figure"],
                layout="constrained",
            )
            self.analytics_canvas = FigureCanvasTkAgg(self.analytics_fig, tab)
            self.analytics_widget = self.analytics_canvas.get_tk_widget()

    # ---- reading holdings.db ----

    def refresh_holdings_display(self):
        """Read the holdings again and show them in every sub-tab."""
        if not HOLDINGS_AVAILABLE or not self.holdings_manager:
            return
        try:
            self.holdings_manager.refresh_holdings()
        except Exception as e:
            print(f"Error refreshing holdings: {e}")
            messagebox.showerror(
                "Long-term Holdings", f"Error reading the holdings: {e}"
            )
            return
        self.show_holdings()
        self.update_portfolio_summary()
        self.show_suggestions()
        self.update_analytics()

    def _holdings(self) -> List["Holding"]:
        return list(getattr(self.holdings_manager, "holdings", None) or [])

    # ---- Holdings ----

    def holding_cells(self, h: "Holding", total: float) -> Tuple[str, ...]:
        share = (
            f"{max(0.0, h.current_value) / total * 100:.2f}%" if total > 0 else "N/A"
        )
        return (
            h.symbol,
            plain_number(h.quantity),
            self._price(h.average_cost),
            self._price(h.current_price),
            self._money(h.total_cost),
            self._money(h.current_value),
            signed_money(h.unrealized_pnl, self._money),
            f"{h.unrealized_pnl_percentage:+.2f}%",
            share,
            f"{h.target_percentage:.1f}%",
            h.exchange,
        )

    def show_holdings(self) -> None:
        """The holdings the search keeps; the selection stays where it can."""
        tree = self.holdings_tree
        selected = set(tree.selection())
        holdings = self._holdings()
        total = sum(max(0.0, h.current_value) for h in holdings)
        tree.delete(*tree.get_children())
        for h in holdings:
            cells = self.holding_cells(h, total)
            if not self.holdings_search.matches(cells):
                continue
            tags = (
                ("profit",)
                if h.unrealized_pnl > 0
                else ("loss",) if h.unrealized_pnl < 0 else ()
            )
            tree.insert("", "end", iid=str(h.id), values=cells, tags=tags)
        keep = [iid for iid in selected if tree.exists(iid)]
        if keep:
            tree.selection_set(keep)
        self.selected_holding = self._selected()
        self.holdings_table.empty.configure(
            text=NO_HOLDINGS_MATCH if holdings else NO_HOLDINGS
        )
        self.holdings_table.settle()

    def _selected(self) -> Optional["Holding"]:
        chosen = {str(iid) for iid in self.holdings_tree.selection()}
        for h in self._holdings():
            if str(h.id) in chosen:
                return h
        return None

    def on_holding_select(self, _event=None):
        self.selected_holding = self._selected()

    # ---- Portfolio Overview ----

    def update_portfolio_summary(self):
        """The totals and the allocation; with no holdings, only the message."""
        holdings = self._holdings()
        _show(self.overview_empty, not holdings)
        _show(self.overview_body, bool(holdings))
        if not holdings:
            if MATPLOTLIB_AVAILABLE:
                self.portfolio_fig.clear()
            return
        summary = self.holdings_manager.get_portfolio_summary()
        labels = self.summary_labels
        labels["holdings_count"].config(text=f"{summary['holdings_count']}")
        labels["total_cost"].config(text=self._money(summary["total_cost"]))
        labels["total_value"].config(text=self._money(summary["total_value"]))
        labels["total_pnl"].config(text=signed_money(summary["total_pnl"], self._money))
        labels["total_pnl_pct"].config(text=f"{summary['total_pnl_percentage']:+.2f}%")
        pnl_style = "Good.TLabel" if summary["total_pnl"] >= 0 else "Bad.TLabel"
        labels["total_pnl"].config(style=pnl_style)
        labels["total_pnl_pct"].config(style=pnl_style)
        self.update_portfolio_chart()

    def _colours(self) -> Dict[str, Any]:
        """One colour per coin, the same in every chart."""
        coins = sorted({h.symbol for h in self._holdings()})
        return {c: plt.cm.Set3(i % 12) for i, c in enumerate(coins)}

    @staticmethod
    def _labels(holdings: Sequence["Holding"]) -> List[str]:
        """A holding's coin, and its exchange when the coin is held in more than one."""
        counts = Counter(h.symbol for h in holdings)
        return [
            (
                f"{h.symbol} ({h.exchange})"
                if counts[h.symbol] > 1 and h.exchange
                else h.symbol
            )
            for h in holdings
        ]

    def update_portfolio_chart(self):
        """The allocation pie: each holding's share of the holdings' current value."""
        if not MATPLOTLIB_AVAILABLE:
            self.chart_note.configure(text=NO_CHARTS)
            _show(self.chart_note, True)
            return
        priced = [h for h in self._holdings() if h.current_value > 0]
        self.portfolio_fig.clear()
        if not priced:
            self.chart_note.configure(text=NO_PRICES)
            _show(self.portfolio_widget, False)
            _show(self.chart_note, True)
            return
        _show(self.chart_note, False)
        _show(self.portfolio_widget, True)
        try:
            chart = ui_tokens.CHART
            size = ui_tokens.CHART_FONT_PT
            colours = self._colours()
            ax = self.portfolio_fig.add_subplot(111)
            _wedges, _texts, autotexts = ax.pie(
                [h.current_value for h in priced],
                labels=self._labels(priced),
                autopct="%1.1f%%",
                colors=[colours[h.symbol] for h in priced],
                textprops={"color": chart["text"], "fontsize": size},
            )
            for autotext in autotexts:  # dark on the pale wedges
                autotext.set_color(chart["figure"])
            ax.set_title(ALLOCATION_TITLE, color=chart["text"], fontsize=size + 1)
            ui_theme.theme_figure(self.portfolio_fig)
            self.portfolio_canvas.draw_idle()
        except Exception as e:
            print(f"Error updating portfolio chart: {e}")

    # ---- Rebalancing ----

    def suggestion_cells(self, s: Dict[str, Any]) -> Tuple[str, ...]:
        return (
            s["symbol"],
            str(s["action"]).capitalize(),
            f"{s['current_percentage']:.2f}%",
            f"{s['target_percentage']:.2f}%",
            f"{s['deviation']:.2f}%",
            self._money(s["amount_difference"]),
        )

    def show_suggestions(self) -> None:
        """The holdings to buy or sell to reach their target %, as the search keeps
        them; worked out from the holdings each time they change."""
        tree = self.suggestions_tree
        tree.delete(*tree.get_children())
        holdings = self._holdings()
        try:
            suggestions = (
                self.holdings_manager.get_rebalancing_suggestions() if holdings else []
            )
        except Exception as e:
            print(f"Error generating suggestions: {e}")
            suggestions = []
        for s in suggestions:
            cells = self.suggestion_cells(s)
            if not self.suggestions_search.matches(cells):
                continue
            tag = "buy" if str(s["action"]).upper() == "BUY" else "sell"
            tree.insert("", "end", values=cells, tags=(tag,))
        if not holdings:
            empty = NO_HOLDINGS
        elif suggestions:
            empty = NO_SUGGESTIONS_MATCH
        elif not any(h.target_percentage > 0 for h in holdings):
            empty = NO_TARGETS
        elif not any(h.current_value > 0 for h in holdings):
            empty = NO_PRICES
        else:
            empty = IN_BALANCE
        self.suggestions_table.empty.configure(text=empty)
        self.suggestions_table.settle()

    # kept for callers of the old button
    generate_rebalancing_suggestions = show_suggestions

    # ---- Analytics ----

    def _price_history(self) -> Dict[str, List[Tuple[datetime, float]]]:
        """The recorded prices of the coins held, with at least two each."""
        try:
            recorded = self.holdings_manager.db.get_price_history()
        except Exception as e:
            print(f"Error reading the price history: {e}")
            return {}
        held = {h.symbol for h in self._holdings()}
        series: Dict[str, List[Tuple[datetime, float]]] = {}
        for symbol, points in recorded.items():
            if symbol not in held:
                continue
            kept = []
            for stamp, value in points:
                try:
                    when = datetime.fromisoformat(str(stamp))
                except ValueError:
                    continue
                if value > 0:
                    kept.append((when, value))
            if len(kept) >= 2:
                series[symbol] = kept
        return series

    def update_analytics(self):
        """Each holding's unrealised P&L %, and the recorded prices as the change
        since each coin's first; with nothing to chart, one message."""
        holdings = self._holdings()
        priced = [h for h in holdings if h.current_price > 0 and h.total_cost > 0]
        series = self._price_history() if holdings else {}
        self.analytics_pnl = [
            (label, h.unrealized_pnl_percentage)
            for label, h in zip(self._labels(priced), priced)
        ]
        self.analytics_prices = {
            symbol: [(value / points[0][1] - 1.0) * 100.0 for _when, value in points]
            for symbol, points in series.items()
        }
        if not MATPLOTLIB_AVAILABLE:
            message = NO_CHARTS if holdings else NO_ANALYTICS
        elif not holdings:
            message = NO_ANALYTICS
        elif not (priced or series):
            message = NO_PRICES
        else:
            message = ""
        if message:
            self.analytics_empty.configure(text=message)
            if MATPLOTLIB_AVAILABLE:
                self.analytics_fig.clear()
                _show(self.analytics_widget, False)
            _show(self.analytics_empty, True)
            return
        _show(self.analytics_empty, False)
        _show(self.analytics_widget, True)
        try:
            self._draw_analytics(series)
        except Exception as e:
            print(f"Error updating analytics charts: {e}")

    def _draw_analytics(self, series: Dict[str, List[Tuple[datetime, float]]]):
        chart, status = ui_tokens.CHART, ui_tokens.STATUS
        size = ui_tokens.CHART_FONT_PT
        fig = self.analytics_fig
        fig.clear()
        count = int(bool(self.analytics_pnl)) + int(bool(series))
        signed = FuncFormatter(lambda v, _pos: f"{v:+.0f}%" if round(v) else "0%")
        column = 1
        if self.analytics_pnl:
            ax = fig.add_subplot(1, count, column)
            column += 1
            labels = [label for label, _pct in self.analytics_pnl]
            values = [pct for _label, pct in self.analytics_pnl]
            ax.bar(
                range(len(values)),
                values,
                color=[status["good"] if v >= 0 else status["bad"] for v in values],
            )
            ax.set_xticks(range(len(values)))
            ax.set_xticklabels(
                labels,
                fontsize=size,
                rotation=90 if len(labels) > LEVEL_LABELS else 0,
            )
            ax.axhline(0.0, color=chart["grid"], linewidth=0.8)
            ax.yaxis.set_major_formatter(signed)
            ax.tick_params(labelsize=size)
            ax.set_title(PNL_TITLE, fontsize=size + 1)
        if series:
            ax = fig.add_subplot(1, count, column)
            colours = self._colours()
            for symbol in sorted(series):
                points = series[symbol]
                ax.plot(
                    [when for when, _value in points],
                    self.analytics_prices[symbol],
                    label=symbol,
                    color=colours.get(symbol, chart["series"]),
                    linewidth=1.5,
                    marker="o",
                    markersize=3,
                )
            ax.axhline(0.0, color=chart["grid"], linewidth=0.8)
            locator = mdates.AutoDateLocator()
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
            ax.yaxis.set_major_formatter(signed)
            ax.tick_params(labelsize=size)
            ax.legend(fontsize=size, loc="best")
            ax.set_title(PRICES_TITLE, fontsize=size + 1)
        ui_theme.theme_figure(fig)
        self.analytics_canvas.draw_idle()

    # kept for callers of the old button
    update_analytics_charts = update_analytics

    # ---- the toolbar ----

    def _coin_list(self) -> List[str]:
        try:
            coins = self._coins() or ()
        except Exception:
            coins = ()
        return [str(c).strip().upper() for c in coins if str(c).strip()]

    def _open_dialog(self, holding: Optional["Holding"]) -> Optional["HoldingDialog"]:
        if self.dialog is not None:
            try:
                if self.dialog.winfo_exists():
                    self.dialog.lift()
                    return self.dialog
            except tk.TclError:
                pass
        self.dialog = HoldingDialog(
            self.main_frame,
            coins=self._coin_list(),
            symbols=self.symbols,
            holding=holding,
            on_save=self.save_holding,
        )
        return self.dialog

    def add_holding_dialog(self) -> Optional["HoldingDialog"]:
        """Open the Add Holding dialog."""
        if not HOLDINGS_AVAILABLE or not self.holdings_manager:
            messagebox.showerror("Add Holding", "The holdings could not be loaded.")
            return None
        if not self._coin_list():
            messagebox.showinfo("Add Holding", "Add a coin in Settings first.")
            return None
        return self._open_dialog(None)

    def edit_holding_dialog(self) -> Optional["HoldingDialog"]:
        """Open the selected holding in the Edit Holding dialog."""
        holding = self._selected()
        if holding is None:
            messagebox.showwarning("Edit Holding", "Select a holding to edit first.")
            return None
        return self._open_dialog(holding)

    def save_holding(self, holding: "Holding") -> bool:
        """Add the dialog's holding to holdings.db, or update it there; whether it
        was saved."""
        holding.last_updated = datetime.now().isoformat()
        if holding.id is None:
            saved = self.holdings_manager.add_holding(holding)
        else:
            saved = self.holdings_manager.update_holding(holding)
        if not saved:
            messagebox.showerror("Long-term Holdings", "The holding was not saved.")
            return False
        self.refresh_holdings_display()
        iid = str(holding.id)
        if self.holdings_tree.exists(iid):
            self.holdings_tree.selection_set(iid)
            self.holdings_tree.see(iid)
            self.selected_holding = self._selected()
        return True

    def delete_holding(self) -> bool:
        """Delete the selected holding, after a confirmation."""
        holding = self._selected()
        if holding is None:
            messagebox.showwarning(
                "Delete Holding", "Select a holding to delete first."
            )
            return False
        what = f"{plain_number(holding.quantity)} {holding.symbol}"
        if holding.exchange:
            what += f" on {holding.exchange}"
        if not messagebox.askyesno("Delete Holding", f"Delete the holding of {what}?"):
            return False
        if not self.holdings_manager.delete_holding(holding.id):
            messagebox.showerror("Delete Holding", "The holding was not deleted.")
            return False
        self.selected_holding = None
        self.refresh_holdings_display()
        return True

    def update_prices_dialog(self):
        """Enter each coin's current price (recorded in the price history)."""
        if not HOLDINGS_AVAILABLE or not self.holdings_manager:
            return
        if not self._holdings():
            messagebox.showinfo("Update Prices", "No holdings yet.")
            return
        dialog = PriceUpdateDialog(self.main_frame, self.holdings_manager)
        if dialog.updated:
            self.refresh_holdings_display()

    def export_holdings(self):
        """Export the holdings to a CSV file."""
        if not HOLDINGS_AVAILABLE or not self.holdings_manager:
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Holdings",
        )
        if file_path:
            if self.holdings_manager.export_holdings_csv(file_path):
                messagebox.showinfo("Export Holdings", f"Exported to {file_path}")
            else:
                messagebox.showerror(
                    "Export Holdings", "The holdings were not exported."
                )

    def export_suggestions(self, file_path: Optional[str] = None) -> bool:
        """Export the suggestions shown, in their order, to a CSV file."""
        tree = self.suggestions_tree
        rows = [tree.item(iid, "values") for iid in tree.get_children()]
        if not rows:
            messagebox.showinfo("Export Suggestions", "No suggestions to export.")
            return False
        if file_path is None:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title="Export Suggestions",
            )
        if not file_path:
            return False
        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([REBALANCE_HEADINGS[c] for c in REBALANCE_COLUMNS])
                writer.writerows(rows)
        except OSError as e:
            messagebox.showerror("Export Suggestions", f"Not exported: {e}")
            return False
        messagebox.showinfo("Export Suggestions", f"Exported to {file_path}")
        return True


class HoldingDialog(tk.Toplevel):
    """Add Holding / Edit Holding; see the module docstring.

    ``coins`` are the hub's coins (a holding of a coin no longer among them keeps
    it); ``symbols`` an ExchangeSymbols; ``holding`` the holding edited (None: a new
    one); ``on_save(holding)`` saves the new or edited Holding and says whether it
    did; the dialog closes once it has."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        coins: Sequence[str],
        symbols: ExchangeSymbols,
        on_save: Callable[["Holding"], bool],
        holding: Optional["Holding"] = None,
    ):
        from pt_exchange_abstraction import exchange_name

        super().__init__(parent)
        self.title("Edit Holding" if holding is not None else "Add Holding")
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.holding = holding
        self.symbols = symbols
        self.on_save = on_save
        self.result: Optional["Holding"] = None
        self.market: Tuple[str, str] = ("", "")

        self.coins = [str(c).strip().upper() for c in coins if str(c).strip()]
        if holding is not None and holding.symbol and holding.symbol not in self.coins:
            self.coins.append(holding.symbol)
        self.exchange_names = [exchange_name(e) for e in symbols.exchanges()]

        def text(value: Any) -> str:
            return plain_number(value) if value else ""

        h = holding
        self.coin_var = tk.StringVar(
            master=self, value=h.symbol if h else (self.coins[0] if self.coins else "")
        )
        self.exchange_var = tk.StringVar(master=self, value=h.exchange if h else "")
        self.quantity_var = tk.StringVar(master=self, value=text(h and h.quantity))
        self.cost_var = tk.StringVar(master=self, value=text(h and h.average_cost))
        self.price_var = tk.StringVar(master=self, value=text(h and h.current_price))
        self.date_var = tk.StringVar(master=self, value=h.purchase_date if h else "")
        self.target_var = tk.StringVar(
            master=self, value=text(h and h.target_percentage)
        )
        self.threshold_var = tk.StringVar(
            master=self, value=plain_number(h.rebalance_threshold if h else 5.0)
        )

        gap = ui_tokens.SPACE["sm"]
        body = ttk.Frame(self, padding=ui_tokens.SPACE["lg"])
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        row = 0

        def field(label: str, widget: tk.Widget) -> None:
            nonlocal row
            ttk.Label(body, text=label).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, gap),
                pady=(0 if row == 0 else gap, 0),
            )
            widget.grid(
                row=row, column=1, sticky="ew", pady=(0 if row == 0 else gap, 0)
            )
            row += 1

        self.coin_box = ttk.Combobox(
            body,
            textvariable=self.coin_var,
            values=self.coins,
            state="readonly",
            width=12,
        )
        field("Coin", self.coin_box)
        self.exchange_box = ttk.Combobox(
            body, textvariable=self.exchange_var, values=self.exchange_names, width=20
        )
        field("Exchange", self.exchange_box)
        self.market_label = ttk.Label(body, text="", style="Muted.TLabel")
        field("Market", self.market_label)
        self.quantity_entry = ttk.Entry(body, textvariable=self.quantity_var, width=20)
        field("Quantity", self.quantity_entry)
        field("Average Cost ($)", ttk.Entry(body, textvariable=self.cost_var, width=20))
        field(
            "Current Price ($)", ttk.Entry(body, textvariable=self.price_var, width=20)
        )
        field("Purchase Date", ttk.Entry(body, textvariable=self.date_var, width=20))
        field("Target %", ttk.Entry(body, textvariable=self.target_var, width=20))
        field(
            "Rebalance Threshold %",
            ttk.Entry(body, textvariable=self.threshold_var, width=20),
        )
        self.notes_text = tk.Text(body, height=3, width=28, wrap="word")
        if h is not None and h.notes:
            self.notes_text.insert("1.0", h.notes)
        field("Notes", self.notes_text)

        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=2, sticky="e", pady=(gap * 2, 0))
        ttk.Button(buttons, text="Save", command=self.save).pack(
            side="left", padx=(0, gap)
        )
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left")

        self.coin_var.trace_add("write", lambda *_: self.update_market())
        self.exchange_var.trace_add("write", lambda *_: self.update_market())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_market()
        self.quantity_entry.focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass  # not viewable yet (a hidden test window)

    def update_market(self) -> None:
        """The coin's market on the exchange chosen (else the primary exchange), in
        that exchange's own symbol format."""
        from pt_exchange_abstraction import exchange_name

        coin = self.coin_var.get().strip()
        if not coin:
            self.market = ("", "")
            self.market_label.configure(text="")
            return
        try:
            self.market = self.symbols.market(coin, self.exchange_var.get())
        except Exception:
            self.market = (coin, "")
        pair, exchange = self.market
        where = f" on {exchange_name(exchange)}" if exchange else ""
        self.market_label.configure(text=f"{pair}{where}")

    def _refuse(self, message: str) -> None:
        messagebox.showerror(self.title(), message, parent=self)

    def save(self) -> Optional["Holding"]:
        """Check the fields and save the holding; the dialog closes once it is."""
        coin = self.coin_var.get().strip().upper()
        if not coin:
            self._refuse("Choose a coin.")
            return None
        try:
            quantity = _number(self.quantity_var.get())
            cost = _number(self.cost_var.get())
            price = _number(self.price_var.get())
            target = _number(self.target_var.get())
            threshold = _number(self.threshold_var.get(), 5.0)
        except ValueError:
            self._refuse("Enter numbers in the number fields.")
            return None
        if quantity <= 0:
            self._refuse("Quantity must be greater than 0.")
            return None
        if cost <= 0:
            self._refuse("Average cost must be greater than 0.")
            return None
        if price < 0:
            self._refuse("Current price cannot be negative.")
            return None
        if not 0.0 <= target <= 100.0:
            self._refuse("Target % must be between 0 and 100.")
            return None
        if threshold < 0:
            self._refuse("Rebalance threshold cannot be negative.")
            return None
        holding = Holding(
            id=self.holding.id if self.holding is not None else None,
            symbol=coin,  # the coin, as holdings.db has always kept it
            quantity=quantity,
            average_cost=cost,
            current_price=price,
            exchange=self.exchange_var.get().strip(),
            purchase_date=self.date_var.get().strip(),
            notes=self.notes_text.get("1.0", tk.END).strip(),
            target_percentage=target,
            rebalance_threshold=threshold,
        )
        if not self.on_save(holding):
            return None
        self.result = holding
        self.destroy()
        return holding


class PriceUpdateDialog:
    """Dialog for updating prices"""

    def __init__(self, parent, holdings_manager):
        self.parent = parent
        self.holdings_manager = holdings_manager
        self.updated = False

        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Update Prices")
        self.dialog.transient(parent.winfo_toplevel())
        self.dialog.grab_set()

        self.setup_dialog()
        self.dialog.wait_window()

    def setup_dialog(self):
        """Setup price update dialog"""
        gap = ui_tokens.SPACE["sm"]
        main_frame = ttk.Frame(self.dialog, padding=ui_tokens.SPACE["lg"])
        main_frame.pack(fill="both", expand=True)

        # Price entries frame
        entries_frame = ttk.Frame(main_frame)
        entries_frame.pack(fill="both", expand=True)

        self.price_entries = {}

        for i, holding in enumerate(self.holdings_manager.holdings):
            if holding.symbol in self.price_entries:
                continue  # one price per coin
            ttk.Label(entries_frame, text=holding.symbol).grid(
                row=i, column=0, sticky="w", padx=(0, gap), pady=(0, gap)
            )
            ttk.Label(entries_frame, text="$").grid(
                row=i, column=1, sticky="e", pady=(0, gap)
            )
            entry = ttk.Entry(entries_frame, width=18)
            entry.grid(row=i, column=2, sticky="ew", pady=(0, gap))
            entry.insert(0, plain_number(holding.current_price))
            self.price_entries[holding.symbol] = entry

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(anchor="e", pady=(gap, 0))

        ttk.Button(
            button_frame, text="Update All", command=self.update_all_prices
        ).pack(side="left", padx=(0, gap))
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(
            side="left"
        )

    def update_all_prices(self):
        """Update all prices"""
        try:
            prices = {s: _number(e.get()) for s, e in self.price_entries.items()}
        except ValueError:
            messagebox.showerror(
                "Update Prices", "Enter a number for each price.", parent=self.dialog
            )
            return
        if any(p <= 0 for p in prices.values()):
            messagebox.showerror(
                "Update Prices",
                "Each price must be greater than 0.",
                parent=self.dialog,
            )
            return
        try:
            for symbol, price in prices.items():
                self.holdings_manager.db.update_price(symbol, price, "manual")
        except Exception as e:
            messagebox.showerror(
                "Update Prices", f"Error updating prices: {e}", parent=self.dialog
            )
            return
        self.updated = True
        self.dialog.destroy()


# Fallback classes for when holdings system is not available
if not HOLDINGS_AVAILABLE:

    class HoldingsManagementGUI:  # noqa: F811
        def __init__(self, parent, **_kwargs):
            self.parent = parent
            ttk.Label(
                parent,
                text="The holdings could not be loaded: "
                "the long_term_holdings module is missing.",
                style="Muted.TLabel",
                anchor="center",
            ).pack(fill="both", expand=True, padx=20, pady=20)
