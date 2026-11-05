"""The hub's Long-term Holdings tab (owner, 2026-11-04).

Manual HODL positions, kept in holdings.db (long_term_holdings) and tracked apart
from the trading account: the account's Value, Buying Power and % in Trade do not
include them, and nothing here reads or changes the paper or live account. Four
sub-tabs:

* Holdings: a toolbar (Add Holding, Edit, Delete, Update Prices, Export CSV,
  Refresh, the tag filter and a search through every column) over the holdings,
  in the shared table (ui_table.DataTable), with their tags and each holding's
  share of the current value of the holdings the tag filter keeps ("% of
  Holdings"); under the table, the totals of the rows shown.
* Portfolio Overview: the holdings' totals beside the allocation, a pie of each
  holding's share of their current value. With no holdings, only "No holdings to
  display".
* Rebalancing: the holdings whose share is further from their target % than their
  rebalance threshold, worked out again whenever the holdings change, in the shared
  table; Export CSV and a search.
* Analytics, from holdings.db: each holding's unrealised P&L % (its current price
  against its average cost) and the prices recorded with Update Prices, as the
  change since each coin's first recorded price. With no holdings, "No data yet".

The tag filter (TagFilter) keeps every holding (All), the untagged ones, or those
with any of the tags chosen; it is one choice for every sub-tab that has it, read
and set from outside with ``tag_selection()``, ``filtered_holdings()`` and
``set_tag_selection()`` (main_frame gets TAG_FILTER_EVENT when it changes).

Add Holding and Edit open HoldingDialog: the coin from the hub's coins (Settings),
the exchange from the exchanges in Settings, primary first (or typed, e.g. a
wallet), and the coin's market on that exchange in the exchange layer's format
(``BTC-USD`` on Coinbase, ``BTCUSDT`` on Binance). holdings.db keeps the coin as
before (``BTC``). The position is entered as a quantity or as the dollar amount
invested (quantity = amount / average cost, to 8 places), the other shown beside
it; the purchase date and time are optional (``YYYY-MM-DD HH:MM``, local time); tags
are added (completed from the tags already used) and removed in the dialog.
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
    from long_term_holdings import (
        UNTAGGED,
        Holding,
        HoldingsManager,
        clean_tags,
        filter_holdings,
        get_holdings_manager,
        quantity_for_amount,
        sorted_tags,
        tags_text,
    )

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
    "tags",
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
    # the share of the current value of the holdings the tag filter keeps, not of
    # the trading account
    "share": "% of Holdings",
    "target_pct": "Target %",
    "exchange": "Exchange",
    "tags": "Tags",
}
HOLDINGS_NUMERIC = tuple(
    c for c in HOLDINGS_COLUMNS if c not in ("symbol", "exchange", "tags")
)
NO_HOLDINGS = "No holdings yet"
NO_HOLDINGS_MATCH = "No holdings match the search"
NO_TAG_MATCH = "No holdings match the tag filter"
# the line under the holdings table: the totals of the rows shown
SHOWN_SUMMARY = (
    ("Holdings", "holdings_count"),
    ("Total Cost", "total_cost"),
    ("Current Value", "total_value"),
    ("P&L", "total_pnl"),
    ("P&L %", "total_pnl_pct"),
)

# ---- the tag filter ----

ALL_LABEL, UNTAGGED_LABEL = "All", "Untagged"
MENU_MARK = "▾"  # after the choice on the filter's button: it opens a menu
FILTER_NAMES = 2  # the filter's button names this many of the tags chosen, then "+n"
TAG_FILTER_EVENT = "<<HoldingsTagFilter>>"  # on main_frame, when the filter changes

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

# ---- the Add / Edit Holding dialog ----

BY_QUANTITY, BY_AMOUNT = "quantity", "amount"  # how the position is entered
DATE_FORMAT, TIME_FORMAT = "%Y-%m-%d", "%H:%M"
DATE_HINT = "YYYY-MM-DD  HH:MM, 24-hour"
NO_TAGS = "No tags"
TAGS_PER_ROW = 4  # the dialog's tag buttons wrap after this many
# keys after which the tag field completes nothing
NO_COMPLETION_KEYS = frozenset(
    ("BackSpace", "Delete", "Left", "Right", "Up", "Down", "Home", "End")
    + ("Return", "KP_Enter", "Tab", "Escape")
)


def split_purchase_date(text: str) -> Tuple[str, str]:
    """A stored purchase date as the dialog's date and time fields: ("2024-01-15",
    "10:30") for "2024-01-15 10:30" (or "2024-01-15T10:30:00"), ("2024-01-15", "")
    for a date alone; text that is not a date stays whole in the date field."""
    text = str(text or "").strip()
    if not text:
        return "", ""
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return text, ""
    clock = when.strftime(TIME_FORMAT) if len(text) > len("2024-01-15") else ""
    return when.strftime(DATE_FORMAT), clock


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


class TagFilter:
    """A sub-tab's tag filter, packed left in a toolbar: "Tags" and a button whose
    menu ticks All, Untagged and each tag in use (``tags()``) as chosen
    (``chosen()``); a click calls ``on_pick(value)``, value None for All, UNTAGGED
    or the tag. The window keeps one choice for every sub-tab's filter."""

    def __init__(
        self,
        bar: tk.Misc,
        *,
        tags: Callable[[], Sequence[str]],
        chosen: Callable[[], Sequence[str]],
        on_pick: Callable[[Optional[str]], None],
    ):
        self._tags, self._chosen, self._on_pick = tags, chosen, on_pick
        self._vars: List[tk.BooleanVar] = []
        self.text = ALL_LABEL
        ttk.Label(bar, text="Tags").pack(side="left", padx=(0, ui_tokens.SPACE["xs"]))
        # a toolbar button (the theme's), whose menu opens under it
        self.button = ttk.Button(bar, command=self.open)
        self.menu = tk.Menu(self.button, tearoff=0)
        self.button.pack(side="left", padx=(0, ui_tokens.SPACE["sm"]))
        self.show(ALL_LABEL)
        self.fill()

    def open(self) -> None:
        """The menu, under the button."""
        self.fill()
        b = self.button
        try:
            self.menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        finally:
            self.menu.grab_release()

    def fill(self) -> None:
        """The menu, from the tags in use and the choice now."""
        menu = self.menu
        menu.delete(0, "end")
        self._vars = []
        chosen = {str(c).casefold() for c in self._chosen()}

        def item(label: str, value: Optional[str], ticked: bool) -> None:
            var = tk.BooleanVar(master=menu, value=ticked)
            self._vars.append(var)
            menu.add_checkbutton(
                label=label, variable=var, command=lambda: self._on_pick(value)
            )

        item(ALL_LABEL, None, not chosen)
        item(UNTAGGED_LABEL, UNTAGGED, UNTAGGED in chosen)
        tags = list(self._tags())
        if tags:
            menu.add_separator()
        for tag in tags:
            item(tag, tag, tag.casefold() in chosen)

    def entries(self) -> List[Tuple[str, bool]]:
        """The menu's items, (label, ticked), as it shows them now (tests)."""
        self.fill()
        labels = [
            self.menu.entrycget(i, "label")
            for i in range(self.menu.index("end") + 1)
            if self.menu.type(i) == "checkbutton"
        ]
        return [(label, bool(v.get())) for label, v in zip(labels, self._vars)]

    def show(self, text: str) -> None:
        """The choice on the button: "All", "Pension, Steve" ..."""
        self.text = text
        self.button.configure(text=f"{text}  {MENU_MARK}")


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
        # the tag filter: the tags chosen (UNTAGGED: the holdings with none), () All
        self._tag_selection: Tuple[str, ...] = ()
        self.tag_filters: List[TagFilter] = []
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

    def _tag_filter(self, bar: tk.Widget) -> TagFilter:
        """A tag filter in ``bar``, showing the window's one choice."""
        tag_filter = TagFilter(
            bar,
            tags=self._tags_in_use,
            chosen=self.tag_selection,
            on_pick=self.pick_tag,
        )
        tag_filter.show(self.tag_filter_text())
        self.tag_filters.append(tag_filter)
        return tag_filter

    def setup_holdings_tab(self):
        """A toolbar (with the tag filter) over the holdings table, and the totals of
        the rows shown under it."""
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
        self.holdings_filter = self._tag_filter(bar)
        self.holdings_search = ui_table.SearchBox(bar, self.show_holdings)
        self.search_var = self.holdings_search.var

        # under the table (packed ahead of it: the table takes the room left)
        self.holdings_summary = ttk.Frame(self.holdings_tab)
        self.shown_labels: Dict[str, ttk.Label] = {}
        for i, (text, key) in enumerate(SHOWN_SUMMARY):
            ttk.Label(self.holdings_summary, text=text, style="Muted.TLabel").pack(
                side="left", padx=(gap * 2 if i else 0, ui_tokens.SPACE["xs"])
            )
            value = ttk.Label(self.holdings_summary, text="")
            value.pack(side="left")
            self.shown_labels[key] = value

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
        # a tag no holding has any more leaves the filter (none left: All)
        before = self._tag_selection
        self._tag_selection = self._valid_selection(before)
        self._show_tag_filter()
        self.show_holdings()
        self.update_portfolio_summary()
        self.show_suggestions()
        self.update_analytics()
        if self._tag_selection != before:
            self._tag_filter_changed()

    def _holdings(self) -> List["Holding"]:
        return list(getattr(self.holdings_manager, "holdings", None) or [])

    # ---- the tag filter (Holdings, Portfolio Overview, Rebalancing) ----

    def tag_selection(self) -> Tuple[str, ...]:
        """The tags the filter keeps, UNTAGGED for the holdings with none; () for
        All."""
        return self._tag_selection

    def filtered_holdings(self) -> List["Holding"]:
        """The holdings the tag filter keeps, in holdings.db's order (by coin)."""
        return filter_holdings(self._holdings(), self._tag_selection)

    def set_tag_selection(self, selection: Optional[Sequence[str]] = ()) -> None:
        """Filter by ``selection``: tags (in any case) and UNTAGGED; () or None for
        All. Tags no holding has are dropped. The sub-tabs the filter applies to show
        the holdings it keeps, and main_frame gets TAG_FILTER_EVENT."""
        self._tag_selection = self._valid_selection(selection)
        self._show_tag_filter()
        self.show_filtered()
        self._tag_filter_changed()

    def pick_tag(self, value: Optional[str]) -> None:
        """A click in a filter's menu: All (None) clears the choice; Untagged or a
        tag joins it, or leaves it when it is in it already."""
        if value is None:
            self.set_tag_selection(())
            return
        chosen = list(self._tag_selection)
        folded = [c.casefold() for c in chosen]
        if value.casefold() in folded:
            del chosen[folded.index(value.casefold())]
        else:
            chosen.append(value)
        self.set_tag_selection(chosen)

    def tag_filter_text(self) -> str:
        """What the filters' buttons show: "All", or the choice ("Untagged",
        "Pension, Steve", "Pension, Steve +1")."""
        names = [UNTAGGED_LABEL if v == UNTAGGED else v for v in self._tag_selection]
        if not names:
            return ALL_LABEL
        more = len(names) - FILTER_NAMES
        shown = ", ".join(names[:FILTER_NAMES])
        return f"{shown} +{more}" if more > 0 else shown

    def _tags_in_use(self) -> List[str]:
        return sorted_tags(t for h in self._holdings() for t in h.tags)

    def _valid_selection(self, selection: Optional[Sequence[str]]) -> Tuple[str, ...]:
        """``selection`` with only UNTAGGED and the tags in use (in their own
        spelling), once each: UNTAGGED first, then the tags alphabetically."""
        in_use = {t.casefold(): t for t in self._tags_in_use()}
        values = [str(v).strip() for v in (selection or ())]
        tags = sorted_tags(
            in_use[v.casefold()] for v in values if v.casefold() in in_use
        )
        return ((UNTAGGED,) if UNTAGGED in values else ()) + tuple(tags)

    def _show_tag_filter(self) -> None:
        text = self.tag_filter_text()
        for tag_filter in self.tag_filters:
            tag_filter.show(text)

    def _tag_filter_changed(self) -> None:
        try:
            self.main_frame.event_generate(TAG_FILTER_EVENT)
        except tk.TclError:
            pass  # the window is gone

    def show_filtered(self) -> None:
        """Show again what the tag filter applies to."""
        self.show_holdings()

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
            tags_text(h.tags),
        )

    def show_holdings(self) -> None:
        """The holdings the tag filter and the search keep, each with its share of
        the current value of those the tag filter keeps, and their totals under the
        table; the selection stays where it can."""
        tree = self.holdings_tree
        selected = set(tree.selection())
        everything = self._holdings()
        holdings = filter_holdings(everything, self._tag_selection)
        total = sum(max(0.0, h.current_value) for h in holdings)
        tree.delete(*tree.get_children())
        shown = []
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
            shown.append(h)
        keep = [iid for iid in selected if tree.exists(iid)]
        if keep:
            tree.selection_set(keep)
        self.selected_holding = self._selected()
        if not everything:
            empty = NO_HOLDINGS
        elif not holdings:
            empty = NO_TAG_MATCH
        else:
            empty = NO_HOLDINGS_MATCH
        self.holdings_table.empty.configure(text=empty)
        self.show_totals(shown)
        self.holdings_table.settle()

    def show_totals(self, shown: Sequence["Holding"]) -> None:
        """The line under the holdings table: the totals of the rows shown (none:
        no line)."""
        self._pack_summary(bool(shown))
        if not shown:
            return
        summary = self.holdings_manager.get_portfolio_summary(list(shown))
        labels = self.shown_labels
        labels["holdings_count"].configure(text=f"{summary['holdings_count']}")
        labels["total_cost"].configure(text=self._money(summary["total_cost"]))
        labels["total_value"].configure(text=self._money(summary["total_value"]))
        pnl_style = "Good.TLabel" if summary["total_pnl"] >= 0 else "Bad.TLabel"
        labels["total_pnl"].configure(
            text=signed_money(summary["total_pnl"], self._money), style=pnl_style
        )
        labels["total_pnl_pct"].configure(
            text=f"{summary['total_pnl_percentage']:+.2f}%", style=pnl_style
        )

    def _pack_summary(self, shown: bool) -> None:
        frame = self.holdings_summary
        if shown and not frame.winfo_manager():
            gap = ui_tokens.SPACE["sm"]
            frame.pack(
                side="bottom",
                fill="x",
                padx=gap,
                pady=(ui_tokens.SPACE["xs"], gap),
                before=self.holdings_table,
            )
        elif not shown and frame.winfo_manager():
            frame.pack_forget()

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
        try:
            used = self.holdings_manager.all_tags()
        except Exception:
            used = []
        self.dialog = HoldingDialog(
            self.main_frame,
            coins=self._coin_list(),
            symbols=self.symbols,
            holding=holding,
            on_save=self.save_holding,
            tags=used,
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
    did; the dialog closes once it has. ``tags`` are the tags already used, which
    the tag field completes and lists."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        coins: Sequence[str],
        symbols: ExchangeSymbols,
        on_save: Callable[["Holding"], bool],
        holding: Optional["Holding"] = None,
        tags: Sequence[str] = (),
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
        self.known_tags = sorted_tags(tags)
        self.tags: List[str] = sorted_tags(holding.tags) if holding is not None else []
        self.tag_buttons: Dict[str, ttk.Button] = {}
        self._working = False  # the quantity or the amount is being worked out

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
        self.entry_mode = tk.StringVar(master=self, value=BY_QUANTITY)
        self.quantity_var = tk.StringVar(master=self, value=text(h and h.quantity))
        self.amount_var = tk.StringVar(
            master=self,
            value=f"{h.total_cost:.2f}" if h and h.total_cost > 0 else "",
        )
        self.cost_var = tk.StringVar(master=self, value=text(h and h.average_cost))
        self.price_var = tk.StringVar(master=self, value=text(h and h.current_price))
        # a purchase date that is not a date (typed before) is kept as it is
        day, clock = split_purchase_date(h.purchase_date if h else "")
        self._kept_date = day if (h and day == (h.purchase_date or "").strip()) else ""
        self.date_var = tk.StringVar(master=self, value=day)
        self.time_var = tk.StringVar(master=self, value=clock)
        self.tag_var = tk.StringVar(master=self)
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
        # the position: a quantity, or the dollars invested; the other is worked out
        modes = ttk.Frame(body)
        for label, value in (("Quantity", BY_QUANTITY), ("Amount ($)", BY_AMOUNT)):
            ttk.Radiobutton(
                modes, text=label, value=value, variable=self.entry_mode
            ).pack(side="left", padx=(0, gap))
        field("Position", modes)
        self.quantity_entry = ttk.Entry(body, textvariable=self.quantity_var, width=20)
        field("Quantity", self.quantity_entry)
        self.amount_entry = ttk.Entry(body, textvariable=self.amount_var, width=20)
        field("Amount Invested ($)", self.amount_entry)
        field("Average Cost ($)", ttk.Entry(body, textvariable=self.cost_var, width=20))
        field(
            "Current Price ($)", ttk.Entry(body, textvariable=self.price_var, width=20)
        )
        when = ttk.Frame(body)
        self.date_entry = ttk.Entry(when, textvariable=self.date_var, width=11)
        self.date_entry.pack(side="left")
        self.time_entry = ttk.Entry(when, textvariable=self.time_var, width=6)
        self.time_entry.pack(side="left", padx=(gap, 0))
        ttk.Label(when, text=DATE_HINT, style="Muted.TLabel").pack(
            side="left", padx=(gap, 0)
        )
        field("Purchase Date", when)
        # the tags: typed (completed from the tags already used) or picked from the
        # list, each shown as a button that removes it
        tag_area = ttk.Frame(body)
        typing = ttk.Frame(tag_area)
        typing.pack(side="top", fill="x")
        self.tag_box = ttk.Combobox(typing, textvariable=self.tag_var, width=18)
        self.tag_box.pack(side="left", fill="x", expand=True)
        ttk.Button(typing, text="Add", command=self.add_tag).pack(
            side="left", padx=(gap, 0)
        )
        self.tags_frame = ttk.Frame(tag_area)
        self.tags_frame.pack(side="top", fill="x", pady=(ui_tokens.SPACE["xs"], 0))
        field("Tags", tag_area)
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
        self.entry_mode.trace_add("write", lambda *_: self.set_entry_mode())
        for var in (self.quantity_var, self.amount_var, self.cost_var):
            var.trace_add("write", lambda *_: self.update_position())
        for key in ("<Return>", "<KP_Enter>", "<<ComboboxSelected>>"):
            self.tag_box.bind(key, self._add_typed_tag)
        self.tag_box.bind("<KeyRelease>", self.complete_tag)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_market()
        self.set_entry_mode()
        self.show_tags()
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

    # ---- the position: a quantity or an amount ----

    def by_amount(self) -> bool:
        return self.entry_mode.get() == BY_AMOUNT

    def set_entry_mode(self) -> None:
        """The field typed in (the quantity or the amount) takes input; the other
        shows what is worked out from it."""
        typed, worked = (
            (self.amount_entry, self.quantity_entry)
            if self.by_amount()
            else (self.quantity_entry, self.amount_entry)
        )
        typed.state(["!disabled"])
        worked.state(["disabled"])

    def update_position(self) -> None:
        """Work out the field not typed in: the quantity from the amount (amount /
        average cost, rounded to 8 places) or the amount from the quantity
        (quantity x average cost)."""
        if self._working:
            return
        self._working = True
        try:
            by_amount = self.by_amount()
            typed = self.amount_var if by_amount else self.quantity_var
            try:
                value, cost = _number(typed.get()), _number(self.cost_var.get())
            except ValueError:
                value, cost = 0.0, 0.0
            worked = ""
            if value > 0 and cost > 0:
                worked = (
                    plain_number(quantity_for_amount(value, cost))
                    if by_amount
                    else f"{value * cost:.2f}"
                )
            (self.quantity_var if by_amount else self.amount_var).set(worked)
        finally:
            self._working = False

    # ---- the tags ----

    def _offered(self) -> List[str]:
        """The tags already used that the holding does not have."""
        own = {t.casefold() for t in self.tags}
        return [t for t in self.known_tags if t.casefold() not in own]

    def _offer(self, typed: str = "") -> None:
        """The tag field's list: the tags offered that hold what is typed."""
        typed = typed.strip().casefold()
        self.tag_box.configure(
            values=[t for t in self._offered() if typed in t.casefold()]
        )

    def add_tag(self, text: Optional[str] = None) -> List[str]:
        """Add ``text``'s tags (None: those typed in the tag field, which is then
        cleared), several separated by commas; a tag already used keeps its own
        spelling. The holding's tags, after."""
        typed = text is None
        text = self.tag_var.get() if typed else text
        spelling = {t.casefold(): t for t in self.known_tags}
        for tag in clean_tags([text]):
            if tag.casefold() not in {t.casefold() for t in self.tags}:
                self.tags.append(spelling.get(tag.casefold(), tag))
        self.tags = sorted_tags(self.tags)
        if typed:
            self.tag_var.set("")
        self.show_tags()
        return list(self.tags)

    def _add_typed_tag(self, _event=None) -> str:
        self.add_tag()
        return "break"

    def remove_tag(self, tag: str) -> List[str]:
        """Take ``tag`` off the holding. The holding's tags, after."""
        self.tags = [t for t in self.tags if t.casefold() != tag.casefold()]
        self.show_tags()
        return list(self.tags)

    def show_tags(self) -> None:
        """A button for each of the holding's tags (a click removes it), or "No
        tags"; the tags already used, less these, in the tag field's list."""
        gap = ui_tokens.SPACE["sm"]
        for child in self.tags_frame.winfo_children():
            child.destroy()
        self.tag_buttons = {}
        if not self.tags:
            ttk.Label(self.tags_frame, text=NO_TAGS, style="Muted.TLabel").grid(
                row=0, column=0, sticky="w"
            )
        for n, tag in enumerate(self.tags):
            button = ttk.Button(
                self.tags_frame,
                text=f"{tag}  ×",
                command=lambda t=tag: self.remove_tag(t),
            )
            button.grid(
                row=n // TAGS_PER_ROW,
                column=n % TAGS_PER_ROW,
                sticky="w",
                padx=(0, gap),
                pady=(0, ui_tokens.SPACE["xs"]),
            )
            self.tag_buttons[tag] = button
        self._offer(self.tag_var.get())

    def complete_tag(self, event=None) -> None:
        """Complete the tag being typed (after the last comma) from the tags already
        used: the rest of the first that starts with it, selected, so the next key
        replaces it. The list shows the tags that hold what is typed."""
        box = self.tag_box
        text = box.get()
        typed = text.rpartition(",")[2].lstrip()
        if event is not None:
            char = getattr(event, "char", "") or ""
            if event.keysym in NO_COMPLETION_KEYS or not char.isprintable():
                self._offer(typed)
                return
        if typed and box.index("insert") == len(text):
            for tag in self._offered():
                if len(tag) > len(typed) and tag.casefold().startswith(
                    typed.casefold()
                ):
                    box.insert("end", tag[len(typed) :])
                    box.selection_range(len(text), "end")
                    box.icursor(len(text))
                    break
        self._offer(typed)

    # ---- saving ----

    def _refuse(self, message: str) -> None:
        messagebox.showerror(self.title(), message, parent=self)

    def purchase_date(self) -> Optional[str]:
        """The purchase date and time as kept: "YYYY-MM-DD HH:MM", "YYYY-MM-DD" or
        "" (neither given); None, after saying why, when they are not a date and a
        time. A purchase date typed before, not a date, is kept as it is."""
        day, clock = self.date_var.get().strip(), self.time_var.get().strip()
        if not day and not clock:
            return ""
        if self._kept_date and day == self._kept_date and not clock:
            return day
        if not day:
            self._refuse("Enter the purchase date for the time.")
            return None
        try:
            when = datetime.strptime(day, DATE_FORMAT)
        except ValueError:
            self._refuse("Enter the purchase date as YYYY-MM-DD.")
            return None
        text = when.strftime(DATE_FORMAT)
        if clock:
            try:
                at = datetime.strptime(clock, TIME_FORMAT)
            except ValueError:
                self._refuse("Enter the purchase time as HH:MM, 24-hour.")
                return None
            when = when.replace(hour=at.hour, minute=at.minute)
            text = when.strftime(f"{DATE_FORMAT} {TIME_FORMAT}")
        if when > datetime.now():
            self._refuse("The purchase date cannot be in the future.")
            return None
        return text

    def save(self) -> Optional["Holding"]:
        """Check the fields and save the holding; the dialog closes once it is."""
        coin = self.coin_var.get().strip().upper()
        if not coin:
            self._refuse("Choose a coin.")
            return None
        by_amount = self.by_amount()
        try:
            quantity = _number(self.quantity_var.get())  # by amount: worked out
            amount = _number(self.amount_var.get()) if by_amount else 0.0
            cost = _number(self.cost_var.get())
            price = _number(self.price_var.get())
            target = _number(self.target_var.get())
            threshold = _number(self.threshold_var.get(), 5.0)
        except ValueError:
            self._refuse("Enter numbers in the number fields.")
            return None
        if by_amount and amount <= 0:
            self._refuse("Amount invested must be greater than 0.")
            return None
        if by_amount and cost <= 0:
            self._refuse("Average cost must be greater than 0.")
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
        purchased = self.purchase_date()
        if purchased is None:
            return None
        if self.tag_var.get().strip():  # typed but not added yet
            self.add_tag()
        holding = Holding(
            id=self.holding.id if self.holding is not None else None,
            symbol=coin,  # the coin, as holdings.db has always kept it
            quantity=quantity,
            average_cost=cost,
            current_price=price,
            exchange=self.exchange_var.get().strip(),
            purchase_date=purchased,
            notes=self.notes_text.get("1.0", tk.END).strip(),
            target_percentage=target,
            rebalance_threshold=threshold,
            tags=list(self.tags),
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
