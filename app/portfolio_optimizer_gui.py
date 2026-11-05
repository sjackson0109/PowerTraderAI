#!/usr/bin/env python3
"""The hub's Portfolio Optimization tab (owner, 2026-11-05).

Modern Portfolio Theory over the coins in Settings (portfolio_optimizer). Sub-tabs:

* Data: where the daily closes come from: the candle cache (the default: the coins
  in Settings over a window of 90 days, 1 year or 3 years, from the exchanges in
  Settings, primary first) or a price file (CSV) picked with Browse. Load Data
  reads them; the table shows each coin's days of closes, last close, annual
  return and volatility, and its share of the current portfolio, and the coins
  left out say why.
* Optimization: the objective (max Sharpe ratio, min variance or a target
  return), the risk-free rate, the weight limits and the coins (those in Settings,
  or only those held); Optimize Portfolio loads the data first when the source,
  the window or the coins in Settings changed since it was loaded, then works out
  the weights and the efficient frontier. The table sets the optimised weights
  beside the current portfolio's and the holdings' target %, under the two
  portfolios' expected return, volatility and Sharpe ratio. Apply as Targets
  writes the optimised weights to the target % of the holdings the tag filter
  keeps, after a confirmation that lists each old and new target; Long-term
  Holdings' Rebalancing (the one rebalancing) then shows the drift from them.
* Analysis.

The current portfolio is Long-term Holdings' (``holdings``: its window, a
HoldingsManagementGUI): the holdings its tag filter keeps, each coin's share of
their current value, worked out again when the filter changes (TAG_FILTER_EVENT).
Holdings of coins with no data are left out of it, and named.

Loading and optimising run off the Tk thread, one job at a time; the window shows
the result when the job ends. A job still running when the window is destroyed is
stopped (between coins, frontier points ...).
"""

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import ui_table
import ui_theme
import ui_tokens

try:
    import portfolio_optimizer as po
    from portfolio_optimizer import PortfolioOptimizer

    OPTIMIZER_AVAILABLE = True
except ImportError:
    OPTIMIZER_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False

try:
    from long_term_holdings_gui import TAG_FILTER_EVENT
except ImportError:
    TAG_FILTER_EVENT = "<<HoldingsTagFilter>>"

SUB_TABS = ("Data", "Optimization", "Analysis")
POLL_MS = 100  # how often the window looks for the end of a job
STOP_WAIT_S = 2.0  # how long a destroyed window waits for its job to stop
FRONTIER_POINTS = 30

# ---- Data ----

SOURCE_LABELS = (
    (po.SOURCE_CANDLES if OPTIMIZER_AVAILABLE else "candles", "Daily candles"),
    (po.SOURCE_FILE if OPTIMIZER_AVAILABLE else "file", "Price file (CSV)"),
)
DATA_COLUMNS = ("coin", "days", "last_close", "annual_return", "annual_vol", "held")
DATA_HEADINGS = {
    "coin": "Coin",
    "days": "Days",
    "last_close": "Last Close",
    "annual_return": "Annual Return %",
    "annual_vol": "Annual Volatility %",
    "held": "% of Holdings",
}
DATA_NUMERIC = DATA_COLUMNS[1:]
NO_DATA = "No data loaded yet"

# ---- Optimization ----

OPTIMIZATION_TYPES = (
    ("Max Sharpe ratio", "max_sharpe"),
    ("Min variance", "min_variance"),
    ("Target return", "target_return"),
)
# the coins optimised over: those in Settings, or only those held
UNIVERSES = (("Coins in Settings", "settings"), ("Coins held", "held"))
RESULT_COLUMNS = ("coin", "held", "optimised", "target")
RESULT_HEADINGS = {
    "coin": "Coin",
    "held": "% of Holdings",
    "optimised": "Optimised %",
    "target": "Target %",  # the holdings' targets now, in Long-term Holdings
}
RESULT_NUMERIC = RESULT_COLUMNS[1:]
NO_RESULT = "Not optimised yet"
METRICS = (
    ("Expected Return (annual)", "expected_return"),
    ("Volatility (annual)", "volatility"),
    ("Sharpe Ratio", "sharpe_ratio"),
)
PORTFOLIOS = (("current", "Current portfolio"), ("optimised", "Optimised"))


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _price(value: float) -> str:
    return "$" + f"{value:,.8f}".rstrip("0").rstrip(".")


def _pct(fraction: float, places: int = 2) -> str:
    return f"{fraction * 100:.{places}f}%"


def _number(text: str) -> Optional[float]:
    """A number typed in a field; None when it is blank. ValueError otherwise."""
    text = str(text).replace(",", "").replace("%", "").strip()
    if not text:
        return None
    number = float(text)
    if not np.isfinite(number):
        raise ValueError(text)
    return number


class _Job:
    """One piece of work off the Tk thread: ``work(job)`` runs in a daemon thread
    and may check ``job.stop`` and set ``job.progress``; the window takes its
    result (or error) on the Tk thread. Neither the job nor ``work`` holds the
    window: a Tk object freed in another thread leaks its interpreter."""

    def __init__(self, name: str, work: Callable[["_Job"], Any]):
        self.name = name
        self.stop = threading.Event()
        self.progress = ""
        self.result: Any = None
        self.error: Optional[BaseException] = None
        self.thread = threading.Thread(
            target=self._run,
            args=(work,),
            name=f"Portfolio Optimization: {name}",
            daemon=True,
        )

    def _run(self, work) -> None:
        try:
            self.result = work(self)
        except BaseException as exc:  # handed to the window
            self.error = exc


def read_data(request: Tuple, load_candles: Callable, job: _Job) -> "po.MarketData":
    """The data ``request`` asks for, ("candles", coins, days) or ("file", path),
    off the Tk thread: ``load_candles`` reads the candles."""
    if request[0] == po.SOURCE_FILE:
        return po.load_price_file(request[1])
    _source, coins, days = request

    def progress(done: int, total: int, coin: str) -> None:
        job.progress = f"Loading daily candles: {coin} ({done + 1} of {total})"

    return load_candles(
        list(coins), days, should_stop=job.stop.is_set, progress=progress
    )


class PortfolioOptimizerGUI:
    """The Portfolio Optimization tab's sub-tabs; see the module docstring.

    ``coins`` gives the coins in Settings; ``holdings`` is Long-term Holdings'
    window (None: no current portfolio); ``optimizer`` a PortfolioOptimizer;
    ``load_candles(coins, days, should_stop=..., progress=...)`` reads the daily
    closes (portfolio_optimizer.load_candle_data); ``money`` and ``price`` format
    amounts and prices."""

    def __init__(
        self,
        parent=None,
        *,
        coins: Callable[[], Sequence[str]] = lambda: (),
        holdings: Any = None,
        optimizer: Optional["PortfolioOptimizer"] = None,
        load_candles: Optional[Callable[..., "po.MarketData"]] = None,
        money: Callable[[float], str] = _money,
        price: Callable[[float], str] = _price,
    ):
        if parent is None:
            self.root = ui_theme.themed_root()
            self.root.title("Portfolio Optimization Engine")
            self.root.geometry("1200x800")
        elif not isinstance(parent, tk.Misc):
            # a stand-in parent (a mock) has no end to its masters: a Tk variable
            # would look for its root for ever
            raise TypeError(f"the parent must be a Tk widget, not {type(parent)}")
        else:
            self.root = parent
        self._coins = coins
        self.holdings = holdings
        self._money, self._price = money, price

        self.optimizer = optimizer
        if self.optimizer is None and OPTIMIZER_AVAILABLE:
            self.optimizer = PortfolioOptimizer()
        self._load_candles = load_candles or (
            po.load_candle_data if OPTIMIZER_AVAILABLE else None
        )

        # GUI state
        self.market_data: Optional["po.MarketData"] = None
        self._loaded_for: Optional[Tuple] = None  # the request market_data answers
        self.current: Optional["po.CurrentPortfolio"] = None
        self.optimization_result: Optional[Dict] = None
        self.result_data: Optional["po.MarketData"] = None  # what the result is over
        self.frontier_data: Optional[pd.DataFrame] = None
        self.job: Optional[_Job] = None
        # takes the job's result, on the Tk thread
        self._done: Optional[Callable] = None
        self._after: Optional[str] = None
        self._closed = False  # the window is destroyed
        self._busy_widgets: List[tk.Widget] = []

        self.setup_gui()
        self.refresh_current()

    def setup_gui(self):
        """The sub-tabs, in a notebook filling the parent."""
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True)
        self.main_frame.bind("<Destroy>", self._on_destroy, add="+")
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill="both", expand=True)

        self.setup_data_tab()
        self.setup_optimization_tab()
        self.setup_analysis_tab()

        if not OPTIMIZER_AVAILABLE:
            for widget in self._busy_widgets:
                widget.state(["disabled"])
            self._say("The optimizer could not be loaded.")
        holdings_frame = getattr(self.holdings, "main_frame", None)
        if holdings_frame is not None:
            holdings_frame.bind(TAG_FILTER_EVENT, self._on_tag_filter, add="+")

    def _on_tag_filter(self, _event=None) -> None:
        if not self._closed:  # Long-term Holdings can outlive this window
            self.refresh_current()

    # ---- the sub-tabs ----

    def _toolbar(self, tab: tk.Widget) -> ttk.Frame:
        gap = ui_tokens.SPACE["sm"]
        bar = ttk.Frame(tab)
        bar.pack(side="top", fill="x", padx=gap, pady=(gap, 0))
        return bar

    def _button(self, bar: tk.Widget, text: str, command: Callable) -> ttk.Button:
        """A toolbar button, disabled while a job runs."""
        button = ttk.Button(bar, text=text, command=command)
        button.pack(side="left", padx=(0, ui_tokens.SPACE["sm"]))
        self._busy_widgets.append(button)
        return button

    def setup_data_tab(self):
        """Where the closes come from, over the coins' table."""
        gap = ui_tokens.SPACE["sm"]
        self.data_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.data_tab, text=SUB_TABS[0])

        bar = self._toolbar(self.data_tab)
        ttk.Label(bar, text="Source").pack(side="left", padx=(0, gap))
        self.source_var = tk.StringVar(master=bar, value=SOURCE_LABELS[0][0])
        for value, label in SOURCE_LABELS:
            ttk.Radiobutton(
                bar, text=label, value=value, variable=self.source_var
            ).pack(side="left", padx=(0, gap))
        ttk.Label(bar, text="Window").pack(side="left", padx=(gap, gap))
        self.window_var = tk.StringVar(
            master=bar, value=po.DEFAULT_WINDOW if OPTIMIZER_AVAILABLE else ""
        )
        self.window_box = ttk.Combobox(
            bar,
            textvariable=self.window_var,
            values=(
                [label for label, _days in po.WINDOWS] if OPTIMIZER_AVAILABLE else []
            ),
            state="readonly",
            width=9,
        )
        self.window_box.pack(side="left", padx=(0, gap * 2))
        self._button(bar, "Load Data", self.load_data)

        file_bar = self._toolbar(self.data_tab)
        ttk.Label(file_bar, text="Price file").pack(side="left", padx=(0, gap))
        self.file_path_var = tk.StringVar(master=file_bar)
        ttk.Entry(file_bar, textvariable=self.file_path_var, width=50).pack(
            side="left", padx=(0, gap)
        )
        self._button(file_bar, "Browse", self.browse_file)

        self.data_status = ttk.Label(self.data_tab, text="", style="Muted.TLabel")
        self.data_status.pack(side="top", fill="x", padx=gap, pady=(gap, 0))
        self.left_out_label = ttk.Label(
            self.data_tab, text="", style="Muted.TLabel", anchor="w"
        )
        self.left_out_label.pack(side="bottom", fill="x", padx=gap, pady=(0, gap))

        self.data_table = ui_table.DataTable(
            self.data_tab,
            DATA_COLUMNS,
            DATA_HEADINGS,
            key="portfolio_optimization.data",
            numeric=DATA_NUMERIC,
            empty_text=NO_DATA,
        )
        self.data_table.pack(side="top", fill="both", expand=True, pady=(gap, 0))
        self.data_tree = self.data_table.tree

    def setup_optimization_tab(self):
        """The objective and limits, the buttons, and the weights."""
        gap = ui_tokens.SPACE["sm"]
        self.optimization_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.optimization_tab, text=SUB_TABS[1])
        tab = self.optimization_tab

        params = ttk.Frame(tab)
        params.pack(side="top", fill="x", padx=gap, pady=(gap, 0))
        self.opt_type_var = tk.StringVar(master=params, value=OPTIMIZATION_TYPES[0][0])
        self.target_return_var = tk.StringVar(master=params)
        self.risk_free_var = tk.StringVar(master=params, value="2.0")
        self.max_weight_var = tk.StringVar(master=params, value="40")
        self.min_weight_var = tk.StringVar(master=params, value="1")
        self.max_vol_var = tk.StringVar(master=params, value="")  # blank: no limit
        self.universe_var = tk.StringVar(master=params, value=UNIVERSES[0][0])

        def field(row: int, column: int, label: str, widget: tk.Widget) -> None:
            ttk.Label(params, text=label).grid(
                row=row, column=column * 2, sticky="w", padx=(0, gap), pady=(0, gap)
            )
            widget.grid(
                row=row,
                column=column * 2 + 1,
                sticky="w",
                padx=(0, gap * 3),
                pady=(0, gap),
            )

        opt_box = ttk.Combobox(
            params,
            textvariable=self.opt_type_var,
            values=[label for label, _key in OPTIMIZATION_TYPES],
            state="readonly",
            width=16,
        )
        opt_box.bind("<<ComboboxSelected>>", self.on_opt_type_change)
        field(0, 0, "Objective", opt_box)
        self.target_return_entry = ttk.Entry(
            params, textvariable=self.target_return_var, width=8
        )
        field(0, 1, "Target Return (annual %)", self.target_return_entry)
        field(
            0,
            2,
            "Risk-free Rate (%)",
            ttk.Entry(params, textvariable=self.risk_free_var, width=8),
        )
        field(
            1,
            0,
            "Max Weight per Coin (%)",
            ttk.Entry(params, textvariable=self.max_weight_var, width=8),
        )
        field(
            1,
            1,
            "Min Weight per Coin (%)",
            ttk.Entry(params, textvariable=self.min_weight_var, width=8),
        )
        field(
            1,
            2,
            "Max Volatility (annual %, blank: none)",
            ttk.Entry(params, textvariable=self.max_vol_var, width=8),
        )
        field(
            2,
            0,
            "Coins",
            ttk.Combobox(
                params,
                textvariable=self.universe_var,
                values=[label for label, _key in UNIVERSES],
                state="readonly",
                width=16,
            ),
        )
        self.on_opt_type_change()

        bar = self._toolbar(tab)
        self._button(bar, "Optimize Portfolio", self.optimize_portfolio)
        self._button(bar, "Apply as Targets", self.apply_as_targets)
        self._button(bar, "Save Portfolio", self.save_portfolio)

        self.current_label = ttk.Label(tab, text="", style="Muted.TLabel", anchor="w")
        self.current_label.pack(side="top", fill="x", padx=gap, pady=(gap, 0))
        self.status_label = ttk.Label(tab, text="", style="Muted.TLabel", anchor="w")
        self.status_label.pack(
            side="top", fill="x", padx=gap, pady=(ui_tokens.SPACE["xs"], 0)
        )

        # the portfolios' figures, under the weights (packed ahead of the table:
        # the table takes the room left)
        metrics = ttk.Frame(tab)
        metrics.pack(
            side="bottom", fill="x", padx=gap, pady=(ui_tokens.SPACE["xs"], gap)
        )
        self.metric_labels: Dict[Tuple[str, str], ttk.Label] = {}
        for column, (key, title) in enumerate(PORTFOLIOS, start=1):
            ttk.Label(metrics, text=title, style="Muted.TLabel").grid(
                row=0, column=column, sticky="e", padx=(gap * 3, 0)
            )
        for row, (title, key) in enumerate(METRICS, start=1):
            ttk.Label(metrics, text=title).grid(row=row, column=0, sticky="w")
            for column, (portfolio, _title) in enumerate(PORTFOLIOS, start=1):
                value = ttk.Label(metrics, text="")
                value.grid(row=row, column=column, sticky="e", padx=(gap * 3, 0))
                self.metric_labels[(portfolio, key)] = value

        self.result_table = ui_table.DataTable(
            tab,
            RESULT_COLUMNS,
            RESULT_HEADINGS,
            key="portfolio_optimization.result",
            numeric=RESULT_NUMERIC,
            empty_text=NO_RESULT,
        )
        self.result_table.pack(side="top", fill="both", expand=True, pady=(gap, 0))
        self.results_tree = self.result_table.tree

    def setup_analysis_tab(self):
        """Setup the analysis and visualization tab."""
        analysis_frame = ttk.Frame(self.notebook)
        self.notebook.add(analysis_frame, text=SUB_TABS[2])

        if not PLOTTING_AVAILABLE:
            tk.Label(
                analysis_frame,
                text="Install matplotlib and seaborn for visualization features",
                font=ui_tokens.font("title"),
            ).pack(pady=50)
            return

        # Visualization controls
        viz_frame = ttk.LabelFrame(analysis_frame, text="Visualization")
        viz_frame.pack(fill=tk.X, padx=10, pady=10)

        viz_buttons = tk.Frame(viz_frame)
        viz_buttons.pack(padx=5, pady=5)

        ttk.Button(
            viz_buttons,
            text="Plot Efficient Frontier",
            command=self.plot_efficient_frontier,
        ).pack(side=tk.LEFT)
        ttk.Button(
            viz_buttons,
            text="Portfolio Composition",
            command=self.plot_portfolio_composition,
        ).pack(side=tk.LEFT, padx=10)
        ttk.Button(
            viz_buttons, text="Risk-Return Scatter", command=self.plot_risk_return
        ).pack(side=tk.LEFT)

        # Chart area
        self.chart_frame = tk.Frame(analysis_frame)
        self.chart_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # ---- jobs off the Tk thread ----

    def _start(self, name: str, work: Callable[[_Job], Any], done: Callable) -> bool:
        """Run ``work`` off the Tk thread and ``done(result)`` on it once it ends;
        False (nothing started) while another job runs."""
        if self.job is not None:
            self._say("Busy: wait for the current job to end.")
            return False
        self.job, self._done = _Job(name, work), done
        self._set_busy(True)
        self.job.thread.start()
        self._poll()
        return True

    def _poll(self) -> None:
        self._after = None
        job = self.job
        if job is None:
            return
        if job.thread.is_alive():
            if job.progress:
                self._say(job.progress)
            try:
                self._after = self.main_frame.after(POLL_MS, self._poll)
            except tk.TclError:
                pass  # the window is gone
            return
        done, self.job, self._done = self._done, None, None
        self._set_busy(False)
        if job.stop.is_set() or isinstance(job.error, po.Stopped):
            return
        if job.error is not None:
            self._failed(job.error)
        else:
            done(job.result)

    def wait(self, timeout: float = 60.0) -> None:
        """Wait for the job running now and show its result (tests)."""
        job = self.job
        if job is None:
            return
        job.thread.join(timeout)
        if self._after is not None:
            try:
                self.main_frame.after_cancel(self._after)
            except tk.TclError:
                pass
        self._poll()

    def close(self) -> None:
        """Stop the job running now (the window is being destroyed)."""
        self._closed = True
        job, self.job, self._done = self.job, None, None
        if self._after is not None:
            try:
                self.main_frame.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        if job is not None:
            job.stop.set()
            job.thread.join(STOP_WAIT_S)

    def _on_destroy(self, event) -> None:
        if event.widget is self.main_frame:
            self.close()

    def _set_busy(self, busy: bool) -> None:
        for widget in self._busy_widgets:
            try:
                widget.state(["disabled"] if busy else ["!disabled"])
            except tk.TclError:
                pass

    def _say(self, text: str) -> None:
        """A line of status, on the Data and Optimization sub-tabs."""
        for label in (self.data_status, self.status_label):
            try:
                label.configure(text=text)
            except tk.TclError:
                pass

    def _failed(self, error: BaseException) -> None:
        self._say(f"Not done: {error}")
        messagebox.showerror("Portfolio Optimization", str(error))

    # ---- the data ----

    def _data_request(self) -> Optional[Tuple]:
        """What Load Data would read now: ("candles", coins, days) or ("file",
        path); None, after saying why, when there is nothing to read."""
        if self.source_var.get() == po.SOURCE_FILE:
            path = self.file_path_var.get().strip()
            if not path:
                messagebox.showerror(
                    "Portfolio Optimization", "Choose a price file first."
                )
                return None
            return (po.SOURCE_FILE, path)
        coins = tuple(self._coin_list())
        if not coins:
            messagebox.showerror(
                "Portfolio Optimization", "Add a coin in Settings first."
            )
            return None
        return (po.SOURCE_CANDLES, coins, po.window_days(self.window_var.get()))

    def _coin_list(self) -> List[str]:
        try:
            coins = self._coins() or ()
        except Exception:
            coins = ()
        return list(
            dict.fromkeys(str(c).strip().upper() for c in coins if str(c).strip())
        )

    def browse_file(self):
        """Pick a price file (and read prices from it)."""
        filename = filedialog.askopenfilename(
            title="Select Price Data File",
            filetypes=[
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx"),
                ("All files", "*.*"),
            ],
        )
        if filename:
            self.file_path_var.set(filename)
            self.source_var.set(po.SOURCE_FILE)

    def load_data(self) -> bool:
        """Read the closes from the source chosen, off the Tk thread."""
        request = self._data_request()
        if request is None:
            return False

        load_candles = self._load_candles

        def work(job: _Job):
            return request, read_data(request, load_candles, job)

        return self._start("load", work, self._loaded)

    def _loaded(self, answer) -> None:
        request, data = answer
        self.market_data, self._loaded_for = data, request
        # a result worked out from other data no longer applies
        self.optimization_result, self.frontier_data = None, None
        self.result_data = None
        self.refresh_current()
        self.show_data()

    def data_summary(self) -> str:
        """The data in one line: the coins and the days they share."""
        data = self.market_data
        if data is None:
            return NO_DATA
        if data.prices.empty:
            return "No coin has enough daily closes."
        days = len(data.prices)
        first, last = data.first_day, data.last_day
        span = f"{first:%Y-%m-%d} to {last:%Y-%m-%d}"
        where = "price file" if data.source == po.SOURCE_FILE else "daily candles"
        n = len(data.coins)
        return f"{n} coin{'' if n == 1 else 's'}, {days} days of {where}, {span}"

    def show_data(self) -> None:
        """The coins' table and the coins left out."""
        tree = self.data_tree
        tree.delete(*tree.get_children())
        data = self.market_data
        held = self.current.weights if self.current is not None else {}
        if data is not None and not data.prices.empty:
            returns, vols = data.expected_returns(), data.volatilities()
            last = data.prices.iloc[-1]
            for coin in data.coins:
                tree.insert(
                    "",
                    "end",
                    iid=coin,
                    values=(
                        coin,
                        str(data.bars.get(coin, len(data.prices))),
                        self._price(float(last[coin])),
                        _pct(float(returns[coin])),
                        _pct(float(vols[coin])),
                        _pct(held[coin]) if coin in held else "",
                    ),
                )
        left = data.left_out if data is not None else {}
        self.left_out_label.configure(
            text=(
                "Left out: " + "; ".join(f"{c} ({why})" for c, why in left.items())
                if left
                else ""
            )
        )
        self.data_status.configure(text=self.data_summary())
        self.data_table.settle()

    # ---- the current portfolio (Long-term Holdings) ----

    def held_holdings(self) -> List[Any]:
        """The holdings Long-term Holdings' tag filter keeps ([] without it)."""
        if self.holdings is None:
            return []
        try:
            return list(self.holdings.filtered_holdings())
        except Exception as e:
            print(f"Error reading the holdings: {e}")
            return []

    def tag_text(self) -> str:
        try:
            return str(self.holdings.tag_filter_text())
        except Exception:
            return "All"

    def refresh_current(self) -> None:
        """The current portfolio again, from the holdings the tag filter keeps, in
        the coins of the data loaded (every coin held before any is)."""
        if not OPTIMIZER_AVAILABLE:
            return
        coins = self.market_data.coins if self.market_data is not None else None
        self.current = po.current_portfolio(self.held_holdings(), coins)
        self.current_label.configure(text=self.current_text())
        if self.market_data is not None:
            self.show_data()
        self.show_result()

    def current_text(self) -> str:
        """The current portfolio in one line."""
        if self.holdings is None:
            return "Current portfolio: Long-term Holdings is not available."
        current = self.current
        tags = self.tag_text()
        if current is None or not current.weights:
            return f"Current portfolio: no holding with a current value (tags: {tags})."
        n = len(current.weights)
        text = (
            f"Current portfolio: Long-term Holdings, tags {tags}: {n} "
            f"coin{'' if n == 1 else 's'}, {self._money(current.value)}"
        )
        if current.outside:
            text += ". Left out, no data: " + ", ".join(
                f"{c} ({_pct(share, 1)} of the holdings' value)"
                for c, share in sorted(current.outside.items())
            )
        return text

    # ---- optimising ----

    def on_opt_type_change(self, event=None):
        """The target return takes input only for a target return objective."""
        wanted = self.opt_type() == "target_return"
        self.target_return_entry.state(["!disabled"] if wanted else ["disabled"])

    def opt_type(self) -> str:
        return dict(OPTIMIZATION_TYPES).get(self.opt_type_var.get(), "max_sharpe")

    def read_parameters(self) -> Optional[Dict[str, Any]]:
        """The objective and limits typed; None, after saying why, when they are
        not numbers in range."""

        def refuse(message: str) -> None:
            messagebox.showerror("Portfolio Optimization", message)

        try:
            risk_free = _number(self.risk_free_var.get()) or 0.0
            top = _number(self.max_weight_var.get())
            bottom = _number(self.min_weight_var.get()) or 0.0
            max_vol = _number(self.max_vol_var.get())
            target = _number(self.target_return_var.get())
        except ValueError:
            refuse("Enter numbers in the number fields.")
            return None
        if top is None or not 0.0 < top <= 100.0:
            refuse("Max weight per coin must be above 0% and at most 100%.")
            return None
        if not 0.0 <= bottom < top:
            refuse("Min weight per coin must be at least 0% and below the max weight.")
            return None
        if max_vol is not None and max_vol <= 0.0:
            refuse("Max volatility must be above 0%, or blank for none.")
            return None
        kind = self.opt_type()
        if kind == "target_return" and target is None:
            refuse("Enter the target return.")
            return None
        return {
            "type": kind,
            "universe": dict(UNIVERSES).get(self.universe_var.get(), "settings"),
            "risk_free_rate": risk_free / 100.0,
            "target_return": target / 100.0 if kind == "target_return" else None,
            "constraints": {
                "max_weight": top / 100.0,
                "min_weight": bottom / 100.0,
                "max_volatility": max_vol / 100.0 if max_vol is not None else None,
            },
        }

    def optimize_portfolio(self) -> bool:
        """Optimise over the data (loaded first when the source, the window or the
        coins in Settings changed), and work out the efficient frontier, off the Tk
        thread."""
        if not OPTIMIZER_AVAILABLE or self.optimizer is None:
            messagebox.showerror(
                "Portfolio Optimization", "The optimizer could not be loaded."
            )
            return False
        params = self.read_parameters()
        if params is None:
            return False
        request = self._data_request()
        if request is None:
            return False
        loaded = self.market_data if request == self._loaded_for else None
        optimizer, load_candles = self.optimizer, self._load_candles
        optimizer.risk_free_rate = params["risk_free_rate"]
        held = None
        if params["universe"] == "held":
            held = {str(h.symbol).strip().upper() for h in self.held_holdings()}

        def work(job: _Job):
            data = (
                loaded if loaded is not None else read_data(request, load_candles, job)
            )
            used = data if held is None else data.only(held)
            problem = po.data_problem(used)
            if problem is None:
                problem = po.constraint_problem(len(used.coins), params["constraints"])
            if problem is not None:
                if held is not None:
                    problem = f"Of the coins held: {problem[0].lower()}{problem[1:]}"
                return request, data, used, problem, None, None
            expected, cov = used.expected_returns(), used.covariance()
            job.progress = "Optimizing"
            result = optimizer.optimize_portfolio(
                expected,
                cov,
                params["type"],
                params["target_return"],
                params["constraints"],
            )
            job.progress = "Working out the efficient frontier"
            frontier = optimizer.calculate_efficient_frontier(
                expected,
                cov,
                FRONTIER_POINTS,
                constraints=params["constraints"],
                should_stop=job.stop.is_set,
            )
            return request, data, used, None, result, frontier

        return self._start("optimize", work, self._optimized)

    def _optimized(self, answer) -> None:
        request, data, used, problem, result, frontier = answer
        if data is not self.market_data:
            self._loaded((request, data))
        if problem is not None:
            self._say(f"Not optimised: {problem}")
            messagebox.showerror("Portfolio Optimization", problem)
            return
        result = dict(result)
        result.pop("optimization_result", None)  # scipy's own, not kept
        result["weights"] = {c: float(w) for c, w in result["weights"].items()}
        self.optimization_result = result
        self.result_data = used  # the coins and days the result is over
        self.frontier_data = frontier
        self.refresh_current()
        self._say(self.result_summary())

    def result_summary(self) -> str:
        result = self.optimization_result
        if result is None:
            return NO_RESULT
        label = {key: label for label, key in OPTIMIZATION_TYPES}.get(
            result.get("method"), result.get("method")
        )
        text = f"Optimised: {label}, over {self.data_summary()}"
        if not result.get("success"):
            text = (
                "Not optimised: "
                + str(result.get("error") or "the optimizer found no solution")
                + "; the weights shown are equal weights"
            )
        return text

    def portfolio_figures(self, weights: Dict[str, float]) -> Optional[Tuple]:
        """(expected return, volatility, Sharpe ratio) of ``weights`` over the data
        the result is over (else the data loaded), annualised; None without data or
        weights."""
        data = self.result_data if self.result_data is not None else self.market_data
        if data is None or data.prices.empty or not weights or self.optimizer is None:
            return None
        coins = data.coins
        w = po.weights_vector(weights, coins)
        if w.sum() <= 0:
            return None
        ret, vol, sharpe = self.optimizer.portfolio_performance(
            w / w.sum(), data.expected_returns().values, data.covariance().values
        )
        return float(ret), float(vol), float(sharpe)

    def show_result(self) -> None:
        """The current and optimised weights, and their figures."""
        tree = self.results_tree
        tree.delete(*tree.get_children())
        result = self.optimization_result
        held = self.current.weights if self.current is not None else {}
        optimised = result["weights"] if result else {}
        targets = self.targets_now()
        coins = list(optimised) or (self.market_data.coins if self.market_data else [])
        coins = list(dict.fromkeys(coins + list(held) + list(targets)))
        for coin in coins:
            tree.insert(
                "",
                "end",
                iid=coin,
                values=(
                    coin,
                    _pct(held[coin]) if coin in held else "",
                    _pct(optimised[coin]) if coin in optimised else "",
                    f"{targets[coin]:.2f}%" if coin in targets else "",
                ),
            )
        figures = {
            "current": self.portfolio_figures(held),
            "optimised": (
                (
                    result["expected_return"],
                    result["volatility"],
                    result["sharpe_ratio"],
                )
                if result
                else None
            ),
        }
        for portfolio, values in figures.items():
            for i, (_title, key) in enumerate(METRICS):
                if values is None:
                    text = ""
                elif key == "sharpe_ratio":
                    text = f"{values[i]:.3f}"
                else:
                    text = _pct(values[i])
                self.metric_labels[(portfolio, key)].configure(text=text)
        self.result_table.settle()

    # ---- Apply as Targets ----

    def targets_now(self) -> Dict[str, float]:
        """Each coin's target % now: the sum of the targets of the holdings the tag
        filter keeps (holdings with no target left out)."""
        targets: Dict[str, float] = {}
        for h in self.held_holdings():
            target = float(getattr(h, "target_percentage", 0.0) or 0.0)
            if target > 0:
                coin = str(h.symbol).strip().upper()
                targets[coin] = targets.get(coin, 0.0) + target
        return targets

    def _holding_names(self, holdings: Sequence[Any]) -> Dict[int, str]:
        """A holding's coin, and its exchange when the coin is held more than once."""
        counts: Dict[str, int] = {}
        for h in holdings:
            counts[h.symbol] = counts.get(h.symbol, 0) + 1
        return {
            id(h): (
                f"{h.symbol} ({h.exchange})"
                if counts[h.symbol] > 1 and h.exchange
                else str(h.symbol)
            )
            for h in holdings
        }

    def apply_as_targets(self) -> bool:
        """Write the optimised weights to the target % of the holdings the tag
        filter keeps (portfolio_optimizer.targets_from_weights), after a
        confirmation listing each old and new target; Long-term Holdings shows them
        at once. Whether they were written."""
        title = "Apply as Targets"
        result = self.optimization_result
        if not result:
            messagebox.showerror(title, "Optimize the portfolio first.")
            return False
        manager = getattr(self.holdings, "holdings_manager", None)
        if manager is None:
            messagebox.showerror(title, "Long-term Holdings is not available.")
            return False
        holdings = self.held_holdings()
        if not holdings:
            messagebox.showerror(
                title, f"No holdings to set targets on (tags: {self.tag_text()})."
            )
            return False
        changes, unheld = po.targets_from_weights(holdings, result["weights"])
        names = self._holding_names(holdings)
        n = len(changes)
        lines = [
            f"Set the target % of {n} holding{'' if n == 1 else 's'} "
            f"(tags: {self.tag_text()}) to the optimised weights?",
            "",
        ]
        lines += [
            f"{names[id(c.holding)]}: {c.old:.2f}% → {c.new:.2f}%" for c in changes
        ]
        if unheld:
            lines += [
                "",
                "Not set, no holding: "
                + ", ".join(f"{c} {w * 100:.2f}%" for c, w in unheld.items()),
            ]
        if not messagebox.askyesno(title, "\n".join(lines)):
            return False
        failed = []
        for change in changes:
            change.holding.target_percentage = change.new
            if not manager.update_holding(change.holding):
                failed.append(names[id(change.holding)])
        try:
            self.holdings.refresh_holdings_display()
        except Exception as e:
            print(f"Error showing the holdings: {e}")
        self.refresh_current()
        if failed:
            messagebox.showerror(title, "Not set: " + ", ".join(failed))
            return False
        self._say(f"Targets set on {n} holding{'' if n == 1 else 's'}.")
        return True

    def save_portfolio(self):
        """Save optimized portfolio."""
        if not self.optimization_result:
            messagebox.showerror("Error", "No optimization result to save")
            return

        # Simple dialog for portfolio name
        name = simpledialog.askstring("Save Portfolio", "Enter portfolio name:")
        if name and OPTIMIZER_AVAILABLE:
            try:
                portfolio_id = self.optimizer.save_optimized_portfolio(
                    name, self.optimization_result, self.opt_type()
                )
                messagebox.showinfo(
                    "Success", f"Portfolio saved with ID {portfolio_id}"
                )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save portfolio: {str(e)}")

    # ---- Analysis ----

    def plot_efficient_frontier(self):
        """Plot efficient frontier."""
        if not PLOTTING_AVAILABLE:
            messagebox.showerror("Error", "Matplotlib not available for plotting")
            return

        if self.frontier_data is None or self.frontier_data.empty:
            messagebox.showerror("Error", "Optimize the portfolio first")
            return

        # Clear previous charts
        for widget in self.chart_frame.winfo_children():
            widget.destroy()

        fig, ax = plt.subplots(figsize=(10, 6))

        # Plot efficient frontier
        ax.plot(
            self.frontier_data["Volatility"],
            self.frontier_data["Return"],
            "-",
            color=ui_tokens.CHART["series"],
            linewidth=2,
            label="Efficient Frontier",
        )

        # Highlight max Sharpe ratio portfolio
        max_sharpe_idx = self.frontier_data["Sharpe_Ratio"].idxmax()
        ax.plot(
            self.frontier_data.loc[max_sharpe_idx, "Volatility"],
            self.frontier_data.loc[max_sharpe_idx, "Return"],
            "o",
            color=ui_tokens.CHART["text"],
            markersize=10,
            label="Max Sharpe Ratio",
        )

        # Mark current optimization if available
        if self.optimization_result:
            ax.plot(
                self.optimization_result["volatility"],
                self.optimization_result["expected_return"],
                "o",
                color=ui_tokens.CHART["series2"],
                markersize=10,
                label="Current Optimization",
            )

        ax.set_xlabel("Volatility (Risk)")
        ax.set_ylabel("Expected Return")
        ax.set_title("Efficient Frontier")
        ax.legend()
        ax.grid(True, alpha=0.3)
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_portfolio_composition(self):
        """Plot portfolio composition pie chart."""
        if not PLOTTING_AVAILABLE:
            messagebox.showerror("Error", "Matplotlib not available for plotting")
            return

        if not self.optimization_result:
            messagebox.showerror("Error", "Please optimize portfolio first")
            return

        # Clear previous charts
        for widget in self.chart_frame.winfo_children():
            widget.destroy()

        fig, ax = plt.subplots(figsize=(8, 8))

        weights = self.optimization_result["weights"]
        assets = list(weights.keys())
        values = list(weights.values())

        colors = plt.cm.Set3(np.arange(len(assets)))
        wedges, texts, autotexts = ax.pie(
            values, labels=assets, autopct="%1.1f%%", colors=colors, startangle=90
        )
        for autotext in autotexts:  # dark on the pale wedges
            autotext.set_color(ui_tokens.CHART["figure"])

        ax.set_title(
            f"Portfolio Composition\n"
            f'Expected Return: {self.optimization_result["expected_return"]:.2%}, '
            f'Volatility: {self.optimization_result["volatility"]:.2%}'
        )
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_risk_return(self):
        """Plot risk-return scatter of individual assets."""
        if not PLOTTING_AVAILABLE:
            messagebox.showerror("Error", "Matplotlib not available for plotting")
            return

        data = self.market_data
        if data is None or data.prices.empty:
            messagebox.showerror("Error", "Please load data first")
            return

        # Clear previous charts
        for widget in self.chart_frame.winfo_children():
            widget.destroy()

        fig, ax = plt.subplots(figsize=(10, 6))

        returns, volatilities = data.expected_returns(), data.volatilities()

        # Plot individual assets
        ax.scatter(volatilities, returns, s=100, alpha=0.7, c=ui_tokens.CHART["series"])

        # Add labels
        for i, asset in enumerate(returns.index):
            ax.annotate(
                asset,
                (volatilities.iloc[i], returns.iloc[i]),
                xytext=(5, 5),
                textcoords="offset points",
            )

        # Add portfolio if optimized
        if self.optimization_result:
            ax.scatter(
                self.optimization_result["volatility"],
                self.optimization_result["expected_return"],
                s=200,
                c=ui_tokens.CHART["series2"],
                marker="*",
                label="Optimized Portfolio",
            )

        ax.set_xlabel("Volatility (Risk)")
        ax.set_ylabel("Expected Return")
        ax.set_title("Risk-Return Profile of Assets")
        ax.grid(True, alpha=0.3)
        if self.optimization_result:
            ax.legend()
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


def main():
    """Run the Portfolio Optimizer GUI."""
    root = ui_theme.themed_root()
    app = PortfolioOptimizerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
