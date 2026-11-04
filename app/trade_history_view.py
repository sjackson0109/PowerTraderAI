"""The hub's Trade History tab: the trade history as a table (owner, 2026-11-04).

Columns: Time, Side, Source, Pair, Quantity, Price, Value, Fees, Realised PnL,
PnL %, from the rows pt_trader writes to trade_history.jsonl (read as before, by
pt_hub; nothing here writes them). Above the table: filters for the coin, side,
source and period, and a search through every column; under them, a summary of the
rows shown (count, fees, realised PnL). A click on a heading sorts by it; newest
first until one is clicked (ui_table.DataTable).

Source is what the row's tag records: a strategy's entry or exit (with the stop
that closed it, when one did), a neural entry or trailing sell, a DCA buy, or a
manual trade. The rows do not record which strategy traded, so the column says
"Strategy" for those.
"""

import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

import ui_table
import ui_tokens

COLUMNS = (
    "time",
    "side",
    "source",
    "pair",
    "qty",
    "price",
    "value",
    "fees",
    "realised",
    "pnl_pct",
)
HEADINGS = {
    "time": "Time",
    "side": "Side",
    "source": "Source",
    "pair": "Pair",
    "qty": "Quantity",
    "price": "Price",
    "value": "Value",
    "fees": "Fees",
    "realised": "Realised PnL",
    "pnl_pct": "PnL %",
}
NUMERIC = ("qty", "price", "value", "fees", "realised", "pnl_pct")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT = "%Y-%m-%d"

ALL = "All"
SIDES = (ALL, "Buy", "Sell")
SOURCES = ("Neural", "Strategy", "DCA", "Manual")
CUSTOM = "Custom range"
PERIODS: Tuple[Tuple[str, Optional[float]], ...] = (
    ("All time", None),
    ("Last 24 hours", 1.0),
    ("Last 7 days", 7.0),
    ("Last 30 days", 30.0),
    ("Last 90 days", 90.0),
    ("Last 12 months", 365.0),
    (CUSTOM, None),
)
EMPTY = "No trades yet"
NO_MATCH = "No trades match these filters"


def _number(value) -> Optional[float]:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _rule_name(rule: str) -> str:
    """The name of the stop an exit row records ("OVL-PLOCK", "stop:OVL-ATR")."""
    rule = rule.split(":", 1)[1] if rule.lower().startswith("stop:") else rule
    try:
        from strategies.descriptions import name_of

        return name_of(rule)
    except Exception:
        return rule


def source_of(row: dict) -> Tuple[str, str]:
    """(source, its text in the table) for one trade_history.jsonl row, from its tag:
    ENTRY and EXIT:<rule> are a strategy's (the rule named when a stop closed the
    trade), DCA a DCA buy, MANUAL a manual trade, no tag or TRAIL_SELL the neural
    trader's entry or trailing sell. Any other tag is shown as it is."""
    tag = str(row.get("tag") or "").strip()
    upper = tag.upper()
    if upper == "DCA":
        return "DCA", "DCA"
    if upper == "MANUAL":
        return "Manual", "Manual"
    if upper == "ENTRY":
        return "Strategy", "Strategy"
    if upper.startswith("EXIT"):
        rule = tag.split(":", 1)[1].strip() if ":" in tag else ""
        if rule and rule.lower() != "strategy":
            return "Strategy", f"Strategy ({_rule_name(rule)})"
        return "Strategy", "Strategy"
    if upper in ("", "TRAIL_SELL"):
        return "Neural", "Neural"
    return tag, tag


@dataclass(frozen=True)
class Trade:
    """One buy or sell of the trade history, as the table shows it."""

    ts: Optional[float]
    side: str  # "Buy" | "Sell"
    source: str  # Neural | Strategy | DCA | Manual | the tag as written
    source_text: str
    pair: str
    coin: str
    qty: Optional[float]
    price: Optional[float]
    fees: Optional[float]
    realised: Optional[float]
    pnl_pct: Optional[float]

    @property
    def value(self) -> Optional[float]:
        if self.qty is None or self.price is None:
            return None
        return self.qty * self.price


def trade_of(row: dict) -> Optional[Trade]:
    """The Trade for one history row; None for a row that is not a buy or sell."""
    side = str(row.get("side", "")).lower().strip()
    if side not in ("buy", "sell"):
        return None
    pair = str(row.get("symbol", "") or "").upper().strip()
    source, text = source_of(row)
    pnl_pct = _number(row.get("pnl_pct"))
    # the PnL % at the trade: a sell's against the average cost, and a DCA buy's
    # (how far below the average cost it bought), as the history list showed them
    if not (side == "sell" or source == "DCA"):
        pnl_pct = None
    return Trade(
        ts=_number(row.get("ts")),
        side=side.capitalize(),
        source=source,
        source_text=text,
        pair=pair,
        coin=pair.split("-")[0].strip(),
        qty=_number(row.get("qty")),
        price=_number(row.get("price")),
        fees=_number(row.get("fees_usd")),
        realised=_number(row.get("realized_profit_usd")) if side == "sell" else None,
        pnl_pct=pnl_pct,
    )


def signed_money(value: float) -> str:
    return f"{'-' if value < 0 else '+'}${abs(value):,.2f}"


def _plain_money(value: float) -> str:
    return f"${value:,.2f}"


def _plain_price(value: float) -> str:
    return f"${value:,.8f}".rstrip("0").rstrip(".")


def _plain_pct(value: float) -> str:
    return f"{value:+.2f}%"


def parse_date(text: str) -> Optional[float]:
    """Local midnight of a YYYY-MM-DD date, as a timestamp."""
    return time.mktime(time.strptime(text.strip(), DATE_FORMAT))


class TradeHistoryView(ttk.Frame):
    """Filters, a summary line and the table, filling ``parent``.

    ``money``, ``price`` and ``pct`` format the cells (pt_hub passes its own, so the
    tab shows numbers as the rest of the hub does)."""

    def __init__(
        self,
        parent: tk.Misc,
        money: Callable[[float], str] = _plain_money,
        price: Callable[[float], str] = _plain_price,
        pct: Callable[[float], str] = _plain_pct,
        now: Callable[[], float] = time.time,
    ):
        super().__init__(parent)
        self._money, self._price, self._pct, self._now = money, price, pct, now
        self.trades: List[Trade] = []
        self.shown: List[Trade] = []
        self._search_after: Optional[str] = None
        gap = ui_tokens.SPACE["sm"]

        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x", padx=gap, pady=(gap, 0))
        self.coin_var = tk.StringVar(value=ALL)
        self.side_var = tk.StringVar(value=ALL)
        self.source_var = tk.StringVar(value=ALL)
        self.period_var = tk.StringVar(value=PERIODS[0][0])
        self.from_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.search_var = tk.StringVar()

        def combo(label: str, var: tk.StringVar, values: Sequence[str], width: int):
            ttk.Label(bar, text=label).pack(side="left", padx=(0, 4))
            box = ttk.Combobox(
                bar,
                textvariable=var,
                values=list(values),
                state="readonly",
                width=width,
            )
            box.pack(side="left", padx=(0, gap + 4))
            return box

        self.coin_box = combo("Coin", self.coin_var, (ALL,), 8)
        self.side_box = combo("Side", self.side_var, SIDES, 5)
        self.source_box = combo("Source", self.source_var, (ALL,) + SOURCES, 9)
        self.period_box = combo("Period", self.period_var, [p for p, _ in PERIODS], 13)
        ttk.Label(bar, text="From").pack(side="left", padx=(0, 4))
        self.from_entry = ttk.Entry(bar, textvariable=self.from_var, width=11)
        self.from_entry.pack(side="left", padx=(0, gap))
        ttk.Label(bar, text="To").pack(side="left", padx=(0, 4))
        self.to_entry = ttk.Entry(bar, textvariable=self.to_var, width=11)
        self.to_entry.pack(side="left", padx=(0, gap + 4))
        ttk.Label(bar, text="Search").pack(side="left", padx=(0, 4))
        self.search_entry = ttk.Entry(bar, textvariable=self.search_var, width=18)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, gap))
        ttk.Button(bar, text="Clear filters", command=self.clear_filters).pack(
            side="left"
        )

        self.summary = ttk.Label(self, anchor="w")
        self.summary.pack(side="top", fill="x", padx=gap, pady=(4, 4))

        self.table = ui_table.DataTable(
            self,
            COLUMNS,
            HEADINGS,
            key="trade_history",
            numeric=NUMERIC,
            sort=("time", True),
            empty_text=EMPTY,
        )
        self.table.pack(side="top", fill="both", expand=True)
        self.tree = self.table.tree

        for var in (self.coin_var, self.side_var, self.source_var, self.to_var):
            var.trace_add("write", lambda *_: self.apply_filters())
        self.from_var.trace_add("write", lambda *_: self.apply_filters())
        self.period_var.trace_add("write", lambda *_: self._period_changed())
        self.search_var.trace_add("write", lambda *_: self._search_changed())
        self._period_changed()

    # ---- the rows ----

    def load(self, rows: Iterable[dict]) -> None:
        """Show the history ``rows`` (trade_history.jsonl's, oldest first)."""
        trades = [t for t in (trade_of(r) for r in rows if isinstance(r, dict)) if t]
        self.trades = sorted(trades, key=lambda t: t.ts or 0.0, reverse=True)
        coins = sorted({t.coin for t in self.trades if t.coin})
        self.coin_box.configure(values=[ALL] + coins)
        if self.coin_var.get() not in [ALL] + coins:
            self.coin_var.set(ALL)
        extra = sorted({t.source for t in self.trades} - set(SOURCES))
        self.source_box.configure(values=[ALL, *SOURCES, *extra])
        self.apply_filters()

    def cells(self, t: Trade) -> Tuple[str, ...]:
        def fmt(value: Optional[float], how: Callable[[float], str]) -> str:
            return "" if value is None else how(value)

        when = (
            time.strftime(TIME_FORMAT, time.localtime(t.ts)) if t.ts is not None else ""
        )
        qty = "" if t.qty is None else f"{t.qty:.8f}".rstrip("0").rstrip(".")
        return (
            when,
            t.side,
            t.source_text,
            t.pair,
            qty,
            fmt(t.price, self._price),
            fmt(t.value, self._money),
            # a fee the trade did not record is unknown, not zero
            "N/A" if t.fees is None else self._money(t.fees),
            fmt(t.realised, signed_money),
            fmt(t.pnl_pct, self._pct),
        )

    # ---- the filters ----

    def _period_changed(self) -> None:
        custom = self.period_var.get() == CUSTOM
        for entry in (self.from_entry, self.to_entry):
            entry.configure(state="normal" if custom else "disabled")
        self.apply_filters()

    def _search_changed(self) -> None:
        if self._search_after is not None:
            try:
                self.after_cancel(self._search_after)
            except tk.TclError:
                pass
        self._search_after = self.after(150, self._search_now)

    def _search_now(self) -> None:
        self._search_after = None
        self.apply_filters()

    def clear_filters(self) -> None:
        for var, value in (
            (self.coin_var, ALL),
            (self.side_var, ALL),
            (self.source_var, ALL),
            (self.period_var, PERIODS[0][0]),
            (self.from_var, ""),
            (self.to_var, ""),
            (self.search_var, ""),
        ):
            var.set(value)
        self.apply_filters()

    def _window(self) -> Tuple[Optional[float], Optional[float], List[str]]:
        """(from, to) timestamps of the period, and what in a custom range could not
        be read."""
        period = self.period_var.get()
        if period != CUSTOM:
            days = dict(PERIODS).get(period)
            return ((self._now() - days * 86400.0) if days else None), None, []
        start = end = None
        problems = []
        for name, var in (("From", self.from_var), ("To", self.to_var)):
            text = var.get().strip()
            if not text:
                continue
            try:
                day = parse_date(text)
            except ValueError:
                problems.append(f"{name}: write the date as YYYY-MM-DD")
                continue
            if name == "From":
                start = day
            else:  # the whole of the To day
                next_day = time.localtime(day + 36 * 3600)[:3]
                end = time.mktime(next_day + (0, 0, 0, 0, 0, -1))
        return start, end, problems

    def matches(self) -> Tuple[List[Trade], List[str]]:
        """The trades the filters keep, and what in them could not be read."""
        coin, side, source = (
            self.coin_var.get(),
            self.side_var.get(),
            self.source_var.get(),
        )
        start, end, problems = self._window()
        words = self.search_var.get().casefold().split()
        kept = []
        for t in self.trades:
            if coin != ALL and t.coin != coin:
                continue
            if side != ALL and t.side != side:
                continue
            if source != ALL and t.source != source:
                continue
            if start is not None and (t.ts is None or t.ts < start):
                continue
            if end is not None and (t.ts is None or t.ts >= end):
                continue
            if words:
                text = " ".join(self.cells(t)).casefold()
                if not all(w in text for w in words):
                    continue
            kept.append(t)
        return kept, problems

    def apply_filters(self) -> None:
        kept, problems = self.matches()
        self.shown = kept
        tree = self.tree
        tree.delete(*tree.get_children())
        for t in kept:
            tree.insert("", "end", values=self.cells(t))
        self.table.empty.configure(text=NO_MATCH if self.trades else EMPTY)
        self.summary.configure(text=self.summary_text(kept, problems))

    def summary_text(self, kept: Sequence[Trade], problems: Sequence[str] = ()) -> str:
        n = len(kept)
        fees = [t.fees for t in kept if t.fees is not None]
        realised = sum(t.realised for t in kept if t.realised is not None)
        parts = [
            f"{n} trade{'' if n == 1 else 's'}",
            f"fees {self._money(sum(fees))}",
            f"realised PnL {signed_money(realised)}",
        ]
        text = ", ".join(parts)
        unknown = n - len(fees)
        if n and unknown:
            text += f" ({unknown} with no fee recorded)"
        if problems:
            text += ". " + "; ".join(problems)
        return text
