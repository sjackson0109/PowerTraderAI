"""
Real-time Market Data Integration (Item 24)
Comprehensive market data feeds supporting multiple exchanges with WebSocket connections
"""

import asyncio
import json
import threading
import time
from collections import defaultdict, deque

# Optional websocket import
try:
    import websocket

    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    websocket = None
import queue
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

try:
    import ccxt
    import ccxt.pro as ccxtpro

    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    print("Warning: CCXT not available. Limited exchange support.")

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("Warning: Pandas not available. Limited data analysis.")

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("Warning: NumPy not available. Limited calculations.")


class DataType(Enum):
    """Types of market data"""

    TICKER = "ticker"
    ORDER_BOOK = "orderbook"
    TRADE = "trade"
    KLINE = "kline"
    FUNDING_RATE = "funding_rate"
    OPEN_INTEREST = "open_interest"


class DataSource(Enum):
    """Market data sources"""

    BINANCE = "binance"
    BINANCE_FUTURES = "binance_futures"
    COINBASE_PRO = "coinbase_pro"
    KRAKEN = "kraken"
    BITFINEX = "bitfinex"
    BYBIT = "bybit"
    DERIBIT = "deribit"
    AGGREGATED = "aggregated"


@dataclass
class MarketTicker:
    """Market ticker data"""

    symbol: str
    exchange: str
    timestamp: datetime
    bid: float
    ask: float
    last: float
    volume: float
    high_24h: float
    low_24h: float
    change_24h: float
    change_24h_pct: float
    vwap: Optional[float] = None

    @property
    def spread(self) -> float:
        """Calculate bid-ask spread"""
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        """Calculate bid-ask spread percentage"""
        if self.ask > 0:
            return (self.spread / self.ask) * 100
        return 0.0


@dataclass
class OrderBookLevel:
    """Order book level (bid/ask)"""

    price: float
    quantity: float
    orders: int = 1

    @property
    def value(self) -> float:
        """Total value at this level"""
        return self.price * self.quantity


@dataclass
class OrderBook:
    """Order book data"""

    symbol: str
    exchange: str
    timestamp: datetime
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]

    def __post_init__(self):
        # Sort bids descending (highest price first)
        self.bids.sort(key=lambda x: x.price, reverse=True)
        # Sort asks ascending (lowest price first)
        self.asks.sort(key=lambda x: x.price)

    @property
    def best_bid(self) -> Optional[OrderBookLevel]:
        """Get best bid price"""
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Optional[OrderBookLevel]:
        """Get best ask price"""
        return self.asks[0] if self.asks else None

    @property
    def spread(self) -> float:
        """Calculate bid-ask spread"""
        if self.best_bid and self.best_ask:
            return self.best_ask.price - self.best_bid.price
        return 0.0

    @property
    def mid_price(self) -> Optional[float]:
        """Calculate mid price"""
        if self.best_bid and self.best_ask:
            return (self.best_bid.price + self.best_ask.price) / 2
        return None

    def get_depth(self, side: str, max_levels: int = 10) -> List[OrderBookLevel]:
        """Get order book depth for specified side"""
        if side.lower() == "bid":
            return self.bids[:max_levels]
        elif side.lower() == "ask":
            return self.asks[:max_levels]
        return []

    def calculate_impact(self, side: str, quantity: float) -> Dict[str, float]:
        """Calculate market impact for given quantity"""
        levels = self.bids if side.lower() == "sell" else self.asks
        remaining_quantity = quantity
        total_cost = 0.0
        weighted_price = 0.0
        levels_consumed = 0

        for level in levels:
            if remaining_quantity <= 0:
                break

            consumed = min(remaining_quantity, level.quantity)
            total_cost += consumed * level.price
            remaining_quantity -= consumed
            levels_consumed += 1

            if remaining_quantity <= 0:
                break

        if total_cost > 0 and quantity > 0:
            weighted_price = total_cost / (quantity - remaining_quantity)

        return {
            "weighted_average_price": weighted_price,
            "total_cost": total_cost,
            "filled_quantity": quantity - remaining_quantity,
            "remaining_quantity": remaining_quantity,
            "levels_consumed": levels_consumed,
            "slippage": abs(
                weighted_price
                - (
                    self.best_bid.price
                    if side.lower() == "sell"
                    else self.best_ask.price
                )
            )
            if weighted_price > 0
            else 0,
        }


@dataclass
class Trade:
    """Trade data"""

    symbol: str
    exchange: str
    timestamp: datetime
    price: float
    quantity: float
    side: str
    trade_id: Optional[str] = None
    buyer_maker: Optional[bool] = None

    @property
    def value(self) -> float:
        """Trade value"""
        return self.price * self.quantity


@dataclass
class Kline:
    """Kline/Candlestick data"""

    symbol: str
    exchange: str
    interval: str
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades_count: int = 0
    taker_buy_volume: Optional[float] = None

    @property
    def body_size(self) -> float:
        """Size of the candlestick body"""
        return abs(self.close - self.open)

    @property
    def upper_shadow(self) -> float:
        """Upper shadow length"""
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        """Lower shadow length"""
        return min(self.open, self.close) - self.low

    @property
    def is_bullish(self) -> bool:
        """Whether the candle is bullish"""
        return self.close > self.open


class MarketDataAggregator:
    """Aggregates and normalizes market data from multiple sources"""

    def __init__(self, db_path: str = "market_data.db"):
        self.db_path = db_path
        self.subscriptions: Dict[str, Set[DataSource]] = defaultdict(set)
        self.data_handlers: Dict[DataType, List[Callable]] = defaultdict(list)
        self.latest_data: Dict[str, Any] = {}
        self.price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.volume_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.active_feeds: Dict[DataSource, bool] = {}
        self.feed_threads: Dict[DataSource, threading.Thread] = {}
        self.running = False

        self._setup_database()

        # CCXT exchanges
        self.exchanges: Dict[DataSource, Any] = {}
        if CCXT_AVAILABLE:
            self._setup_ccxt_exchanges()

    def _setup_database(self):
        """Setup SQLite database for market data storage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Ticker data table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tickers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                bid REAL,
                ask REAL,
                last REAL,
                volume REAL,
                high_24h REAL,
                low_24h REAL,
                change_24h REAL,
                change_24h_pct REAL,
                vwap REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Order book table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS order_books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                level_index INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Trades table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                side TEXT NOT NULL,
                trade_id TEXT,
                buyer_maker INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Klines table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS klines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                interval TEXT NOT NULL,
                open_time DATETIME NOT NULL,
                close_time DATETIME NOT NULL,
                open_price REAL NOT NULL,
                high_price REAL NOT NULL,
                low_price REAL NOT NULL,
                close_price REAL NOT NULL,
                volume REAL NOT NULL,
                trades_count INTEGER,
                taker_buy_volume REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange, interval, open_time)
            )
        """
        )

        # Create indexes for better performance
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickers_symbol_exchange_time ON tickers(symbol, exchange, timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_trades_symbol_exchange_time ON trades(symbol, exchange, timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_klines_symbol_exchange_interval_time ON klines(symbol, exchange, interval, open_time)"
        )

        conn.commit()
        conn.close()

    def _setup_ccxt_exchanges(self):
        """Setup CCXT exchange connections"""
        try:
            # Binance Spot
            self.exchanges[DataSource.BINANCE] = ccxt.binance(
                {
                    "apiKey": "",
                    "secret": "",
                    "sandbox": False,
                    "enableRateLimit": True,
                }
            )

            # Binance Futures
            self.exchanges[DataSource.BINANCE_FUTURES] = ccxt.binance(
                {
                    "apiKey": "",
                    "secret": "",
                    "sandbox": False,
                    "enableRateLimit": True,
                    "options": {"defaultType": "future"},
                }
            )

            # Coinbase Pro
            self.exchanges[DataSource.COINBASE_PRO] = ccxt.coinbase(
                {
                    "apiKey": "",
                    "secret": "",
                    "passphrase": "",
                    "sandbox": False,
                    "enableRateLimit": True,
                }
            )

            # Kraken
            self.exchanges[DataSource.KRAKEN] = ccxt.kraken(
                {
                    "apiKey": "",
                    "secret": "",
                    "enableRateLimit": True,
                }
            )

        except Exception as e:
            print(f"Error setting up CCXT exchanges: {e}")

    def subscribe(
        self, symbol: str, data_types: List[DataType], exchanges: List[DataSource]
    ):
        """Subscribe to market data for a symbol"""
        key = f"{symbol}_{','.join([dt.value for dt in data_types])}"
        for exchange in exchanges:
            self.subscriptions[key].add(exchange)

        # Start feeds if not already running
        for exchange in exchanges:
            if exchange not in self.active_feeds:
                self.start_feed(exchange)

    def unsubscribe(
        self,
        symbol: str,
        data_types: List[DataType],
        exchanges: List[DataSource] = None,
    ):
        """Unsubscribe from market data"""
        key = f"{symbol}_{','.join([dt.value for dt in data_types])}"

        if exchanges is None:
            # Remove all subscriptions for this symbol/data type
            if key in self.subscriptions:
                del self.subscriptions[key]
        else:
            # Remove specific exchanges
            for exchange in exchanges:
                self.subscriptions[key].discard(exchange)

    def add_data_handler(self, data_type: DataType, handler: Callable):
        """Add a handler for specific data type"""
        self.data_handlers[data_type].append(handler)

    def remove_data_handler(self, data_type: DataType, handler: Callable):
        """Remove a data handler"""
        if handler in self.data_handlers[data_type]:
            self.data_handlers[data_type].remove(handler)

    def start_feed(self, exchange: DataSource):
        """Start market data feed for an exchange"""
        if exchange in self.active_feeds and self.active_feeds[exchange]:
            return  # Already running

        if not WEBSOCKET_AVAILABLE:
            print(f"WebSocket not available - {exchange.value} feed disabled")
            self.active_feeds[exchange] = False
            return

        self.active_feeds[exchange] = True

        if exchange == DataSource.BINANCE:
            thread = threading.Thread(target=self._binance_feed, daemon=True)
        elif exchange == DataSource.COINBASE_PRO:
            thread = threading.Thread(target=self._coinbase_feed, daemon=True)
        elif exchange == DataSource.KRAKEN:
            thread = threading.Thread(target=self._kraken_feed, daemon=True)
        else:
            print(f"Feed not implemented for {exchange}")
            return

        self.feed_threads[exchange] = thread
        thread.start()
        print(f"Started {exchange.value} market data feed")

    def stop_feed(self, exchange: DataSource):
        """Stop market data feed for an exchange"""
        self.active_feeds[exchange] = False
        if exchange in self.feed_threads:
            # Thread will stop on next iteration
            print(f"Stopping {exchange.value} market data feed")

    def stop_all_feeds(self):
        """Stop all market data feeds"""
        self.running = False
        for exchange in list(self.active_feeds.keys()):
            self.stop_feed(exchange)

    def _binance_feed(self):
        """Binance WebSocket feed"""
        if not WEBSOCKET_AVAILABLE:
            print("WebSocket not available - Binance feed disabled")
            self.active_feeds[DataSource.BINANCE] = False
            return

        try:

            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    self._process_binance_message(data)
                except Exception as e:
                    print(f"Error processing Binance message: {e}")

            def on_error(ws, error):
                print(f"Binance WebSocket error: {error}")

            def on_close(ws, close_status_code, close_msg):
                print("Binance WebSocket connection closed")
                if self.active_feeds.get(DataSource.BINANCE, False):
                    # Attempt to reconnect
                    time.sleep(5)
                    self.start_feed(DataSource.BINANCE)

            # Connect to Binance WebSocket
            ws_url = "wss://stream.binance.com:9443/ws/btcusdt@ticker/ethusdt@ticker/adausdt@ticker"
            ws = websocket.WebSocketApp(
                ws_url, on_message=on_message, on_error=on_error, on_close=on_close
            )

            ws.run_forever()

        except Exception as e:
            print(f"Error in Binance feed: {e}")
            self.active_feeds[DataSource.BINANCE] = False

    def _coinbase_feed(self):
        """Coinbase Pro WebSocket feed"""
        if not WEBSOCKET_AVAILABLE:
            print("WebSocket not available - Coinbase feed disabled")
            self.active_feeds[DataSource.COINBASE_PRO] = False
            return

        try:

            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    self._process_coinbase_message(data)
                except Exception as e:
                    print(f"Error processing Coinbase message: {e}")

            def on_error(ws, error):
                print(f"Coinbase WebSocket error: {error}")

            def on_close(ws, close_status_code, close_msg):
                print("Coinbase WebSocket connection closed")
                if self.active_feeds.get(DataSource.COINBASE_PRO, False):
                    time.sleep(5)
                    self.start_feed(DataSource.COINBASE_PRO)

            def on_open(ws):
                # Subscribe to ticker data
                subscribe_message = {
                    "type": "subscribe",
                    "product_ids": ["BTC-USD", "ETH-USD", "ADA-USD"],
                    "channels": ["ticker", "level2"],
                }
                ws.send(json.dumps(subscribe_message))

            ws_url = "wss://ws-feed.exchange.coinbase.com"
            ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open,
            )

            ws.run_forever()

        except Exception as e:
            print(f"Error in Coinbase feed: {e}")
            self.active_feeds[DataSource.COINBASE_PRO] = False

    def _kraken_feed(self):
        """Kraken WebSocket feed"""
        # Placeholder for Kraken WebSocket implementation
        print("Kraken feed not yet implemented")
        self.active_feeds[DataSource.KRAKEN] = False

    def _process_binance_message(self, data: Dict):
        """Process Binance WebSocket message"""
        try:
            if "e" in data and data["e"] == "24hrTicker":
                # 24hr ticker statistics
                ticker = MarketTicker(
                    symbol=data["s"],
                    exchange=DataSource.BINANCE.value,
                    timestamp=datetime.fromtimestamp(data["E"] / 1000),
                    bid=float(data["b"]),
                    ask=float(data["a"]),
                    last=float(data["c"]),
                    volume=float(data["v"]),
                    high_24h=float(data["h"]),
                    low_24h=float(data["l"]),
                    change_24h=float(data["P"]),
                    change_24h_pct=float(data["p"]),
                )

                self._update_ticker(ticker)

        except Exception as e:
            print(f"Error processing Binance message: {e}")

    def _process_coinbase_message(self, data: Dict):
        """Process Coinbase Pro WebSocket message"""
        try:
            if data.get("type") == "ticker":
                # Ticker update
                ticker = MarketTicker(
                    symbol=data["product_id"].replace("-", ""),
                    exchange=DataSource.COINBASE_PRO.value,
                    timestamp=datetime.fromisoformat(
                        data["time"].replace("Z", "+00:00")
                    ),
                    bid=float(data["best_bid"]),
                    ask=float(data["best_ask"]),
                    last=float(data["price"]),
                    volume=float(data["volume_24h"]),
                    high_24h=float(data["high_24h"]),
                    low_24h=float(data["low_24h"]),
                    change_24h=0.0,  # Calculate from previous data
                    change_24h_pct=0.0,  # Calculate from previous data
                )

                self._update_ticker(ticker)

            elif data.get("type") == "l2update":
                # Level 2 order book update
                self._update_order_book_coinbase(data)

        except Exception as e:
            print(f"Error processing Coinbase message: {e}")

    def _update_ticker(self, ticker: MarketTicker):
        """Update ticker data and notify handlers"""
        key = f"{ticker.symbol}_{ticker.exchange}"
        self.latest_data[f"ticker_{key}"] = ticker

        # Update price history
        self.price_history[key].append(
            {
                "timestamp": ticker.timestamp,
                "price": ticker.last,
                "volume": ticker.volume,
            }
        )

        # Store in database
        self._store_ticker(ticker)

        # Notify handlers
        for handler in self.data_handlers[DataType.TICKER]:
            try:
                handler(ticker)
            except Exception as e:
                print(f"Error in ticker handler: {e}")

    def _update_order_book_coinbase(self, data: Dict):
        """Update order book from Coinbase L2 update"""
        # Placeholder for order book processing
        pass

    def _store_ticker(self, ticker: MarketTicker):
        """Store ticker data in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO tickers (
                    symbol, exchange, timestamp, bid, ask, last, volume,
                    high_24h, low_24h, change_24h, change_24h_pct, vwap
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    ticker.symbol,
                    ticker.exchange,
                    ticker.timestamp,
                    ticker.bid,
                    ticker.ask,
                    ticker.last,
                    ticker.volume,
                    ticker.high_24h,
                    ticker.low_24h,
                    ticker.change_24h,
                    ticker.change_24h_pct,
                    ticker.vwap,
                ),
            )

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error storing ticker data: {e}")

    def get_latest_ticker(
        self, symbol: str, exchange: str = None
    ) -> Optional[MarketTicker]:
        """Get latest ticker data"""
        if exchange:
            key = f"ticker_{symbol}_{exchange}"
            return self.latest_data.get(key)
        else:
            # Return best ticker across all exchanges
            best_ticker = None
            for key, ticker in self.latest_data.items():
                if key.startswith(f"ticker_{symbol}_") and isinstance(
                    ticker, MarketTicker
                ):
                    if best_ticker is None or ticker.timestamp > best_ticker.timestamp:
                        best_ticker = ticker
            return best_ticker

    def get_price_history(
        self, symbol: str, exchange: str = None, minutes: int = 60
    ) -> List[Dict]:
        """Get price history for the last N minutes"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        if exchange:
            key = f"{symbol}_{exchange}"
            history = list(self.price_history[key])
        else:
            # Aggregate from all exchanges
            history = []
            for key, data in self.price_history.items():
                if key.startswith(f"{symbol}_"):
                    history.extend(data)

        # Filter by time and sort
        filtered = [h for h in history if h["timestamp"] >= cutoff_time]
        filtered.sort(key=lambda x: x["timestamp"])

        return filtered

    def calculate_vwap(
        self, symbol: str, exchange: str = None, minutes: int = 60
    ) -> Optional[float]:
        """Calculate Volume Weighted Average Price"""
        history = self.get_price_history(symbol, exchange, minutes)

        if not history:
            return None

        total_volume_price = sum(h["price"] * h["volume"] for h in history)
        total_volume = sum(h["volume"] for h in history)

        if total_volume > 0:
            return total_volume_price / total_volume
        return None

    def get_spread_analysis(self, symbol: str) -> Dict[str, Any]:
        """Analyze spreads across exchanges"""
        analysis = {
            "exchanges": {},
            "best_bid": None,
            "best_ask": None,
            "arbitrage_opportunities": [],
        }

        best_bid_price = 0
        best_ask_price = float("inf")
        best_bid_exchange = None
        best_ask_exchange = None

        for key, data in self.latest_data.items():
            if key.startswith(f"ticker_{symbol}_") and isinstance(data, MarketTicker):
                exchange = data.exchange
                analysis["exchanges"][exchange] = {
                    "bid": data.bid,
                    "ask": data.ask,
                    "spread": data.spread,
                    "spread_pct": data.spread_pct,
                    "last_update": data.timestamp,
                }

                # Track best bid/ask across exchanges
                if data.bid > best_bid_price:
                    best_bid_price = data.bid
                    best_bid_exchange = exchange

                if data.ask < best_ask_price:
                    best_ask_price = data.ask
                    best_ask_exchange = exchange

        analysis["best_bid"] = {"price": best_bid_price, "exchange": best_bid_exchange}
        analysis["best_ask"] = {"price": best_ask_price, "exchange": best_ask_exchange}

        # Find arbitrage opportunities
        if best_bid_price > best_ask_price:
            analysis["arbitrage_opportunities"].append(
                {
                    "buy_exchange": best_ask_exchange,
                    "sell_exchange": best_bid_exchange,
                    "buy_price": best_ask_price,
                    "sell_price": best_bid_price,
                    "profit_per_unit": best_bid_price - best_ask_price,
                    "profit_pct": ((best_bid_price - best_ask_price) / best_ask_price)
                    * 100,
                }
            )

        return analysis


class MarketDataManager:
    """Main market data management interface"""

    def __init__(self, db_path: str = "market_data.db"):
        self.aggregator = MarketDataAggregator(db_path)
        self.active_subscriptions: Dict[str, Dict] = {}
        self.update_callbacks: List[Callable] = []

        # Setup default handlers
        self.aggregator.add_data_handler(DataType.TICKER, self._on_ticker_update)

    def start(self):
        """Start the market data manager"""
        self.aggregator.running = True
        print("Market Data Manager started")

    def stop(self):
        """Stop the market data manager"""
        self.aggregator.stop_all_feeds()
        print("Market Data Manager stopped")

    def add_update_callback(self, callback: Callable):
        """Add callback for data updates"""
        self.update_callbacks.append(callback)

    def remove_update_callback(self, callback: Callable):
        """Remove update callback"""
        if callback in self.update_callbacks:
            self.update_callbacks.remove(callback)

    def subscribe_symbol(self, symbol: str, exchanges: List[str] = None):
        """Subscribe to real-time data for a symbol"""
        if exchanges is None:
            exchanges = [DataSource.BINANCE.value, DataSource.COINBASE_PRO.value]

        exchange_sources = []
        for exchange_name in exchanges:
            try:
                exchange_sources.append(DataSource(exchange_name))
            except ValueError:
                print(f"Unknown exchange: {exchange_name}")

        self.aggregator.subscribe(
            symbol, [DataType.TICKER, DataType.ORDER_BOOK], exchange_sources
        )

        self.active_subscriptions[symbol] = {
            "exchanges": exchanges,
            "subscribed_at": datetime.now(),
        }

        print(f"Subscribed to {symbol} on {', '.join(exchanges)}")

    def unsubscribe_symbol(self, symbol: str):
        """Unsubscribe from symbol data"""
        self.aggregator.unsubscribe(symbol, [DataType.TICKER, DataType.ORDER_BOOK])
        if symbol in self.active_subscriptions:
            del self.active_subscriptions[symbol]
        print(f"Unsubscribed from {symbol}")

    def get_current_price(self, symbol: str, exchange: str = None) -> Optional[float]:
        """Get current price for symbol"""
        ticker = self.aggregator.get_latest_ticker(symbol, exchange)
        return ticker.last if ticker else None

    def get_market_summary(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive market summary"""
        ticker = self.aggregator.get_latest_ticker(symbol)
        if not ticker:
            return {}

        history = self.aggregator.get_price_history(symbol, minutes=60)
        vwap = self.aggregator.calculate_vwap(symbol, minutes=60)
        spread_analysis = self.aggregator.get_spread_analysis(symbol)

        return {
            "symbol": symbol,
            "current_price": ticker.last,
            "bid": ticker.bid,
            "ask": ticker.ask,
            "spread": ticker.spread,
            "spread_pct": ticker.spread_pct,
            "volume_24h": ticker.volume,
            "high_24h": ticker.high_24h,
            "low_24h": ticker.low_24h,
            "change_24h": ticker.change_24h,
            "change_24h_pct": ticker.change_24h_pct,
            "vwap_1h": vwap,
            "last_update": ticker.timestamp,
            "data_points_1h": len(history),
            "spread_analysis": spread_analysis,
        }

    def _on_ticker_update(self, ticker: MarketTicker):
        """Handle ticker updates"""
        # Notify all callbacks
        for callback in self.update_callbacks:
            try:
                callback("ticker", ticker)
            except Exception as e:
                print(f"Error in update callback: {e}")


# Global market data manager instance
_market_data_manager = None


def get_market_data_manager() -> MarketDataManager:
    """Get global market data manager instance"""
    global _market_data_manager
    if _market_data_manager is None:
        _market_data_manager = MarketDataManager()
    return _market_data_manager


def initialize_market_data():
    """Initialize market data system"""
    manager = get_market_data_manager()
    manager.start()
    return manager


# Example usage and testing
if __name__ == "__main__":
    # Initialize market data
    manager = initialize_market_data()

    # Add update callback
    def on_market_update(data_type: str, data: Any):
        if data_type == "ticker":
            print(f"Price update: {data.symbol} @ {data.last} ({data.exchange})")

    manager.add_update_callback(on_market_update)

    # Subscribe to symbols
    manager.subscribe_symbol("BTCUSDT", ["binance"])
    manager.subscribe_symbol("BTC-USD", ["coinbase_pro"])

    try:
        # Run for 30 seconds
        time.sleep(30)

        # Get market summaries
        btc_summary = manager.get_market_summary("BTCUSDT")
        print(f"BTC Summary: {btc_summary}")

    finally:
        manager.stop()
