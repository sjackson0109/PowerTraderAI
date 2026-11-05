"""
Long-term Holdings Management System (Item 20)
Manages cryptocurrency portfolios with long-term investment tracking

Tags (owner, 2026-11-04): each holding has none, one or more free-text labels
("Steve", "Pension"), kept in holdings.db's ``holding_tags`` table, one row per
holding and tag. The table is created when holdings.db is opened if it is not there
yet; the ``holdings`` table and its rows are left exactly as they are, so a holding
from before has no tags. Tags compare without regard to case and hold no commas.
A tag selection (``filter_holdings``) keeps the holdings with any of its tags;
UNTAGGED in it keeps those with none, and an empty one keeps every holding.

Fees (owner, 2026-11-05): a rebalancing suggestion carries the fee of its trade at
the taker rate ``trading_fee_rate`` gives: the exchange layer's
``trading_fees(symbol)`` where the layer has it, else DEFAULT_TAKER_FEE_RATE.
"""

import json
import math
import os
import re
import sqlite3
import tkinter as tk
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("Warning: pandas not available. Some features will be limited.")

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available. Chart features disabled.")


@contextmanager
def _connect(path: str):
    """A connection that commits on success, rolls back on error and is always
    closed. sqlite3's own ``with`` only commits: the connection stays open, and on
    Windows the file stays locked, until the garbage collector frees it."""
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


# ---- tags ----

UNTAGGED = ""  # in a tag selection: the holdings with no tags (no tag is blank)
TAG_SEPARATOR = ", "  # between a holding's tags in the table and the CSV export
QUANTITY_DECIMALS = 8  # a quantity worked out from an amount is rounded to this
EXPORT_COLUMNS = (  # Export CSV's columns, in order
    "Symbol",
    "Quantity",
    "Average Cost",
    "Current Price",
    "Total Cost",
    "Current Value",
    "Unrealized P&L",
    "P&L %",
    "Exchange",
    "Purchase Date",
    "Tags",
    "Target %",
    "Notes",
)


def clean_tags(tags: Iterable[str]) -> List[str]:
    """``tags`` as kept: each trimmed, its inner spaces made single, commas split it,
    blanks dropped, and only the first of tags differing only in case."""
    kept: List[str] = []
    seen = set()
    for text in tags or ():
        for part in str(text).split(","):
            tag = re.sub(r"\s+", " ", part).strip()
            if tag and tag.casefold() not in seen:
                seen.add(tag.casefold())
                kept.append(tag)
    return kept


def sorted_tags(tags: Iterable[str]) -> List[str]:
    return sorted(clean_tags(tags), key=lambda t: (t.casefold(), t))


def tags_text(tags: Iterable[str]) -> str:
    """A holding's tags in one line, in alphabetical order: "Pension, Steve"."""
    return TAG_SEPARATOR.join(sorted_tags(tags))


def matches_tags(holding: "Holding", selection: Iterable[str] = ()) -> bool:
    """Whether ``holding`` is kept by the tag selection: any of its tags is in it
    (UNTAGGED: it has none); an empty selection keeps every holding."""
    wanted = {str(t).strip().casefold() for t in selection or ()}
    if not wanted:
        return True
    own = {t.casefold() for t in clean_tags(holding.tags)}
    if not own:
        return UNTAGGED in wanted
    return bool(own & wanted)


def filter_holdings(
    holdings: Iterable["Holding"], selection: Iterable[str] = ()
) -> List["Holding"]:
    """The holdings the tag selection keeps, in their order (see matches_tags)."""
    selection = tuple(selection or ())
    return [h for h in holdings if matches_tags(h, selection)]


# ---- fees, through the exchange layer ----

DEFAULT_TAKER_FEE_RATE = (
    0.006  # 0.6%: the taker rate when the exchange layer gives none
)
MAX_FEE_RATE = 0.1  # a "rate" of 10% or more is not taken as a fee rate


def trading_fee_rate(
    symbol: str, layer: Optional[Callable[[], Any]] = None
) -> Tuple[float, bool]:
    """The taker fee rate for trading ``symbol`` (a fraction: 0.006 is 0.6%) and
    whether the exchange layer gave it: the layer's ``trading_fees(symbol)`` (the
    selected exchange's maker and taker rates, as fractions) when it has that
    method, else DEFAULT_TAKER_FEE_RATE. ``layer`` gives the exchange layer
    (default: pt_multi_exchange.market_exchanges). The one place fees are read."""
    try:
        if layer is None:
            from pt_multi_exchange import market_exchanges as layer
        source = layer()
        fees = getattr(source, "trading_fees", None)
        if not callable(fees):
            fees = getattr(
                getattr(source, "exchange_manager", None), "trading_fees", None
            )
        if callable(fees):
            answer = fees(symbol)
            # the managers answer with a Sourced whose value is the TradingFees
            if hasattr(getattr(answer, "value", None), "taker"):
                answer = answer.value
            taker = (
                answer.get("taker")
                if isinstance(answer, dict)
                else getattr(answer, "taker", None)
            )
            rate = float(taker)
            if math.isfinite(rate) and 0.0 <= rate < MAX_FEE_RATE:
                return rate, True
    except Exception as e:
        print(f"No trading fee from the exchange layer for {symbol}: {e}")
    return DEFAULT_TAKER_FEE_RATE, False


def quantity_for_amount(amount: float, average_cost: float) -> float:
    """The quantity ``amount`` dollars buy at ``average_cost`` dollars a coin,
    rounded half up to QUANTITY_DECIMALS places; ValueError unless the cost is
    above 0."""
    if not average_cost > 0:
        raise ValueError("the average cost must be greater than 0")
    step = Decimal(1).scaleb(-QUANTITY_DECIMALS)
    exact = Decimal(str(amount)) / Decimal(str(average_cost))
    return float(exact.quantize(step, rounding=ROUND_HALF_UP))


@dataclass
class Holding:
    """Represents a long-term cryptocurrency holding"""

    id: Optional[int] = None
    symbol: str = ""
    quantity: float = 0.0
    average_cost: float = 0.0
    current_price: float = 0.0
    exchange: str = ""
    # "YYYY-MM-DD" or "YYYY-MM-DD HH:MM" (local time) from the dialog; "" unknown.
    # Older rows keep whatever was typed.
    purchase_date: str = ""
    notes: str = ""
    target_percentage: float = 0.0
    rebalance_threshold: float = 5.0  # Percentage deviation before rebalancing
    last_updated: str = ""
    tags: List[str] = field(default_factory=list)  # holding_tags; [] untagged

    @property
    def total_cost(self) -> float:
        return self.quantity * self.average_cost

    @property
    def current_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.current_value - self.total_cost

    @property
    def unrealized_pnl_percentage(self) -> float:
        if self.total_cost == 0:
            return 0.0
        return (self.unrealized_pnl / self.total_cost) * 100


class HoldingsDatabase:
    """Database management for long-term holdings"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            import pt_paths

            db_path = pt_paths.data_file("holdings.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database tables"""
        with _connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS holdings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    average_cost REAL NOT NULL,
                    current_price REAL DEFAULT 0.0,
                    exchange TEXT DEFAULT '',
                    purchase_date TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    target_percentage REAL DEFAULT 0.0,
                    rebalance_threshold REAL DEFAULT 5.0,
                    last_updated TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    source TEXT DEFAULT 'manual'
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rebalance_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_value REAL NOT NULL,
                    rebalance_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    notes TEXT DEFAULT ''
                )
            """)

            # The tags (2026-11-04): a table of their own, so a holdings.db from
            # before only gains it, empty; its holdings rows stay as they are.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS holding_tags (
                    holding_id INTEGER NOT NULL,
                    tag TEXT NOT NULL COLLATE NOCASE,
                    PRIMARY KEY (holding_id, tag)
                )
            """)
            conn.commit()

    @staticmethod
    def _write_tags(conn: sqlite3.Connection, holding_id: int, tags) -> None:
        """Replace the tags of holding ``holding_id`` with ``tags`` (clean_tags)."""
        conn.execute("DELETE FROM holding_tags WHERE holding_id=?", (holding_id,))
        conn.executemany(
            "INSERT OR IGNORE INTO holding_tags (holding_id, tag) VALUES (?, ?)",
            [(holding_id, tag) for tag in clean_tags(tags)],
        )

    def add_holding(self, holding: Holding) -> int:
        """Add a new holding to the database"""
        with _connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO holdings (symbol, quantity, average_cost, current_price,
                                    exchange, purchase_date, notes, target_percentage,
                                    rebalance_threshold, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    holding.symbol,
                    holding.quantity,
                    holding.average_cost,
                    holding.current_price,
                    holding.exchange,
                    holding.purchase_date,
                    holding.notes,
                    holding.target_percentage,
                    holding.rebalance_threshold,
                    holding.last_updated,
                ),
            )
            holding_id = cursor.lastrowid
            self._write_tags(conn, holding_id, holding.tags)
            conn.commit()
            return holding_id

    def update_holding(self, holding: Holding):
        """Update an existing holding"""
        with _connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE holdings
                SET symbol=?, quantity=?, average_cost=?, current_price=?,
                    exchange=?, purchase_date=?, notes=?, target_percentage=?,
                    rebalance_threshold=?, last_updated=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """,
                (
                    holding.symbol,
                    holding.quantity,
                    holding.average_cost,
                    holding.current_price,
                    holding.exchange,
                    holding.purchase_date,
                    holding.notes,
                    holding.target_percentage,
                    holding.rebalance_threshold,
                    holding.last_updated,
                    holding.id,
                ),
            )
            if holding.id is not None and cursor.rowcount:  # the holding is there
                self._write_tags(conn, holding.id, holding.tags)
            conn.commit()

    def delete_holding(self, holding_id: int):
        """Delete a holding (and its tags) from the database"""
        with _connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM holdings WHERE id=?", (holding_id,))
            cursor.execute("DELETE FROM holding_tags WHERE holding_id=?", (holding_id,))
            conn.commit()

    def get_all_holdings(self) -> List[Holding]:
        """Retrieve all holdings from the database"""
        with _connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM holdings ORDER BY symbol")
            rows = cursor.fetchall()
            tags: Dict[int, List[str]] = {}
            for holding_id, tag in cursor.execute(
                "SELECT holding_id, tag FROM holding_tags ORDER BY holding_id, rowid"
            ):
                tags.setdefault(holding_id, []).append(tag)

            holdings = []
            for row in rows:
                holding = Holding(
                    id=row[0],
                    symbol=row[1],
                    quantity=row[2],
                    average_cost=row[3],
                    current_price=row[4],
                    exchange=row[5],
                    purchase_date=row[6],
                    notes=row[7],
                    target_percentage=row[8],
                    rebalance_threshold=row[9],
                    last_updated=row[10],
                    tags=sorted_tags(tags.get(row[0], ())),
                )
                holdings.append(holding)
            return holdings

    def update_price(self, symbol: str, price: float, source: str = "manual"):
        """Update the current price for a symbol"""
        timestamp = datetime.now().isoformat()

        with _connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Update current price in holdings
            cursor.execute(
                """
                UPDATE holdings
                SET current_price=?, last_updated=?, updated_at=CURRENT_TIMESTAMP
                WHERE symbol=?
            """,
                (price, timestamp, symbol),
            )

            # Add to price history
            cursor.execute(
                """
                INSERT INTO price_history (symbol, price, timestamp, source)
                VALUES (?, ?, ?, ?)
            """,
                (symbol, price, timestamp, source),
            )
            conn.commit()

    def get_price_history(self) -> Dict[str, List[Tuple[str, float]]]:
        """The prices recorded for each symbol (update_price), oldest first:
        {symbol: [(timestamp, price), ...]}. Reads only."""
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT symbol, timestamp, price FROM price_history"
                " ORDER BY timestamp, id"
            ).fetchall()
        history: Dict[str, List[Tuple[str, float]]] = {}
        for symbol, timestamp, price in rows:
            history.setdefault(symbol, []).append((timestamp, float(price)))
        return history


class HoldingsManager:
    """Main manager for long-term holdings operations"""

    def __init__(self, db_path: Optional[str] = None):
        # None: holdings.db in the user data folder (pt_paths)
        self.db = HoldingsDatabase(db_path)
        self.holdings: List[Holding] = []
        self.refresh_holdings()

    def refresh_holdings(self):
        """Refresh holdings from database"""
        self.holdings = self.db.get_all_holdings()

    def add_holding(self, holding: Holding) -> bool:
        """Add a new holding"""
        try:
            holding_id = self.db.add_holding(holding)
            holding.id = holding_id
            self.refresh_holdings()
            return True
        except Exception as e:
            print(f"Error adding holding: {e}")
            return False

    def update_holding(self, holding: Holding) -> bool:
        """Update an existing holding"""
        try:
            self.db.update_holding(holding)
            self.refresh_holdings()
            return True
        except Exception as e:
            print(f"Error updating holding: {e}")
            return False

    def delete_holding(self, holding_id: int) -> bool:
        """Delete a holding"""
        try:
            self.db.delete_holding(holding_id)
            self.refresh_holdings()
            return True
        except Exception as e:
            print(f"Error deleting holding: {e}")
            return False

    # ---- tags ----

    def all_tags(self) -> List[str]:
        """Every tag the holdings have, once each (whatever its case), in
        alphabetical order."""
        return sorted_tags(t for h in self.holdings for t in h.tags)

    def filter_by_tags(self, selection: Iterable[str] = ()) -> List[Holding]:
        """The holdings the tag selection keeps: those with any of its tags, the
        untagged ones for UNTAGGED, and every holding for an empty selection."""
        return filter_holdings(self.holdings, selection)

    def _chosen(self, holdings: Optional[Sequence[Holding]]) -> List[Holding]:
        return list(self.holdings if holdings is None else holdings)

    def get_portfolio_summary(
        self, holdings: Optional[Sequence[Holding]] = None
    ) -> Dict[str, float]:
        """Get overall portfolio summary (of ``holdings``, e.g. filter_by_tags;
        None: every holding)"""
        holdings = self._chosen(holdings)
        total_cost = sum(h.total_cost for h in holdings)
        total_value = sum(h.current_value for h in holdings)
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

        return {
            "total_cost": total_cost,
            "total_value": total_value,
            "total_pnl": total_pnl,
            "total_pnl_percentage": total_pnl_pct,
            "holdings_count": len(holdings),
        }

    def get_rebalancing_suggestions(
        self,
        holdings: Optional[Sequence[Holding]] = None,
        fee_rate: Optional[Callable[[str], float]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate rebalancing suggestions based on target allocations: each
        holding's share of the current value of ``holdings`` (e.g. filter_by_tags;
        None: every holding) against its target %. ``fee_rate(symbol)`` is the
        taker rate (a fraction) of the trade: each suggestion has its fee and its
        net amount (a buy's amount and fee, a sell's amount less its fee); None:
        no fee."""
        holdings = self._chosen(holdings)
        suggestions = []
        portfolio_value = sum(h.current_value for h in holdings)

        if portfolio_value == 0:
            return suggestions

        for holding in holdings:
            if holding.target_percentage > 0:
                current_percentage = (holding.current_value / portfolio_value) * 100
                target_value = (holding.target_percentage / 100) * portfolio_value
                current_value = holding.current_value

                deviation = abs(current_percentage - holding.target_percentage)

                if deviation >= holding.rebalance_threshold:
                    action = (
                        "BUY"
                        if current_percentage < holding.target_percentage
                        else "SELL"
                    )
                    amount_diff = abs(target_value - current_value)
                    rate = float(fee_rate(holding.symbol)) if fee_rate else 0.0
                    fee = amount_diff * rate

                    suggestions.append(
                        {
                            "symbol": holding.symbol,
                            "action": action,
                            "current_percentage": current_percentage,
                            "target_percentage": holding.target_percentage,
                            "deviation": deviation,
                            "amount_difference": amount_diff,
                            "suggested_value": target_value,
                            "fee_rate": rate,
                            "fee": fee,
                            "net_amount": (
                                amount_diff + fee
                                if action == "BUY"
                                else amount_diff - fee
                            ),
                        }
                    )

        return sorted(suggestions, key=lambda x: x["deviation"], reverse=True)

    @staticmethod
    def export_row(holding: Holding) -> Dict[str, Any]:
        """A holding as one row of the CSV export (EXPORT_COLUMNS)."""
        return {
            "Symbol": holding.symbol,
            "Quantity": holding.quantity,
            "Average Cost": holding.average_cost,
            "Current Price": holding.current_price,
            "Total Cost": holding.total_cost,
            "Current Value": holding.current_value,
            "Unrealized P&L": holding.unrealized_pnl,
            "P&L %": holding.unrealized_pnl_percentage,
            "Exchange": holding.exchange,
            "Purchase Date": holding.purchase_date,
            "Tags": tags_text(holding.tags),
            "Target %": holding.target_percentage,
            "Notes": holding.notes,
        }

    def export_holdings_csv(
        self, file_path: str, holdings: Optional[Sequence[Holding]] = None
    ) -> bool:
        """Export holdings to CSV file (``holdings``, e.g. filter_by_tags; None:
        every holding)"""
        rows = [self.export_row(h) for h in self._chosen(holdings)]
        try:
            if PANDAS_AVAILABLE:
                df = pd.DataFrame(rows, columns=list(EXPORT_COLUMNS))
                df.to_csv(file_path, index=False)
                return True
            else:
                # Fallback CSV writing without pandas
                import csv

                with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=list(EXPORT_COLUMNS))
                    writer.writeheader()
                    writer.writerows(rows)
                return True
        except Exception as e:
            print(f"Error exporting to CSV: {e}")
            return False


# Global instance
_holdings_manager = None


def get_holdings_manager() -> HoldingsManager:
    """Get the global holdings manager instance"""
    global _holdings_manager
    if _holdings_manager is None:
        _holdings_manager = HoldingsManager()
    return _holdings_manager
