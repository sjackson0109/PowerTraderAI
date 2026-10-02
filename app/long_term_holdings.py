"""
Long-term Holdings Management System (Item 20)
Manages cryptocurrency portfolios with long-term investment tracking
"""

import json
import os
import sqlite3
import tkinter as tk
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple

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


@dataclass
class Holding:
    """Represents a long-term cryptocurrency holding"""

    id: Optional[int] = None
    symbol: str = ""
    quantity: float = 0.0
    average_cost: float = 0.0
    current_price: float = 0.0
    exchange: str = ""
    purchase_date: str = ""
    notes: str = ""
    target_percentage: float = 0.0
    rebalance_threshold: float = 5.0  # Percentage deviation before rebalancing
    last_updated: str = ""

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
        with sqlite3.connect(self.db_path) as conn:
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
            conn.commit()

    def add_holding(self, holding: Holding) -> int:
        """Add a new holding to the database"""
        with sqlite3.connect(self.db_path) as conn:
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
            conn.commit()
            return cursor.lastrowid

    def update_holding(self, holding: Holding):
        """Update an existing holding"""
        with sqlite3.connect(self.db_path) as conn:
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
            conn.commit()

    def delete_holding(self, holding_id: int):
        """Delete a holding from the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM holdings WHERE id=?", (holding_id,))
            conn.commit()

    def get_all_holdings(self) -> List[Holding]:
        """Retrieve all holdings from the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM holdings ORDER BY symbol")
            rows = cursor.fetchall()

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
                )
                holdings.append(holding)
            return holdings

    def update_price(self, symbol: str, price: float, source: str = "manual"):
        """Update the current price for a symbol"""
        timestamp = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
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

    def get_portfolio_summary(self) -> Dict[str, float]:
        """Get overall portfolio summary"""
        total_cost = sum(h.total_cost for h in self.holdings)
        total_value = sum(h.current_value for h in self.holdings)
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

        return {
            "total_cost": total_cost,
            "total_value": total_value,
            "total_pnl": total_pnl,
            "total_pnl_percentage": total_pnl_pct,
            "holdings_count": len(self.holdings),
        }

    def get_rebalancing_suggestions(self) -> List[Dict[str, Any]]:
        """Generate rebalancing suggestions based on target allocations"""
        suggestions = []
        portfolio_value = sum(h.current_value for h in self.holdings)

        if portfolio_value == 0:
            return suggestions

        for holding in self.holdings:
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

                    suggestions.append(
                        {
                            "symbol": holding.symbol,
                            "action": action,
                            "current_percentage": current_percentage,
                            "target_percentage": holding.target_percentage,
                            "deviation": deviation,
                            "amount_difference": amount_diff,
                            "suggested_value": target_value,
                        }
                    )

        return sorted(suggestions, key=lambda x: x["deviation"], reverse=True)

    def export_holdings_csv(self, file_path: str) -> bool:
        """Export holdings to CSV file"""
        try:
            if PANDAS_AVAILABLE:
                data = []
                for holding in self.holdings:
                    data.append(
                        {
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
                            "Target %": holding.target_percentage,
                            "Notes": holding.notes,
                        }
                    )

                df = pd.DataFrame(data)
                df.to_csv(file_path, index=False)
                return True
            else:
                # Fallback CSV writing without pandas
                import csv

                with open(file_path, "w", newline="") as csvfile:
                    fieldnames = [
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
                        "Target %",
                        "Notes",
                    ]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()

                    for holding in self.holdings:
                        writer.writerow(
                            {
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
                                "Target %": holding.target_percentage,
                                "Notes": holding.notes,
                            }
                        )
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
