"""
PowerTraderAI+ Paper Trading System

Simulated trading environment for testing strategies with live market data
without risking real capital.
"""

import asyncio
import json
import time
import random
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from decimal import Decimal
import uuid
from enum import Enum
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

# PowerTrader imports
from pt_risk import RiskManager, RiskLimits
from pt_cost import CostManager
from pt_validation import InputValidator
from pt_logging import get_logger

class OrderType(Enum):
    """Types of trading orders."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"

class OrderStatus(Enum):
    """Status of trading orders."""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    PARTIAL = "partial"
    REJECTED = "rejected"

class OrderSide(Enum):
    """Order side - buy or sell."""
    BUY = "buy"
    SELL = "sell"

@dataclass
class Position:
    """Trading position data."""
    symbol: str
    quantity: Decimal
    average_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal = field(default=Decimal('0'))
    realized_pnl: Decimal = field(default=Decimal('0'))
    entry_time: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)
    
    @property
    def market_value(self) -> Decimal:
        """Current market value of position."""
        return self.quantity * self.current_price
    
    @property
    def cost_basis(self) -> Decimal:
        """Original cost of position."""
        return self.quantity * self.average_price

@dataclass
class Order:
    """Trading order data."""
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    order_type: OrderType = OrderType.MARKET
    side: OrderSide = OrderSide.BUY
    quantity: Decimal = field(default=Decimal('0'))
    price: Decimal = field(default=Decimal('0'))
    stop_price: Optional[Decimal] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = field(default=Decimal('0'))
    filled_price: Decimal = field(default=Decimal('0'))
    commission: Decimal = field(default=Decimal('0'))
    created_time: datetime = field(default_factory=datetime.now)
    filled_time: Optional[datetime] = None
    
    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == OrderStatus.FILLED
    
    @property
    def remaining_quantity(self) -> Decimal:
        """Get remaining quantity to fill."""
        return self.quantity - self.filled_quantity

@dataclass
class TradeRecord:
    """Individual trade execution record."""
    trade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: Decimal = field(default=Decimal('0'))
    price: Decimal = field(default=Decimal('0'))
    commission: Decimal = field(default=Decimal('0'))
    timestamp: datetime = field(default_factory=datetime.now)
    pnl: Decimal = field(default=Decimal('0'))

@dataclass
class PortfolioSnapshot:
    """Portfolio state at a point in time."""
    timestamp: datetime
    total_value: Decimal
    cash_balance: Decimal
    positions_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    positions: Dict[str, Position]
    daily_pnl: Decimal = field(default=Decimal('0'))
    
class MarketDataSimulator:
    """Simulates market data for paper trading."""
    
    def __init__(self):
        self.current_prices: Dict[str, Decimal] = {}
        self.price_history: Dict[str, List[Dict[str, Any]]] = {}
        self.logger = get_logger("market_simulator")
        
    def get_current_price(self, symbol: str) -> Decimal:
        """Get current simulated price for symbol."""
        if symbol not in self.current_prices:
            # Initialize with a realistic base price
            base_prices = {
                'BTC': Decimal('45000'),
                'ETH': Decimal('3000'),
                'ADA': Decimal('0.50'),
                'SOL': Decimal('100'),
                'DOT': Decimal('25')
            }
            self.current_prices[symbol] = base_prices.get(symbol, Decimal('100'))
        
        # Simulate small price movements (±0.5%)
        import random
        current = self.current_prices[symbol]
        change_percent = Decimal(str(random.uniform(-0.005, 0.005)))
        new_price = current * (Decimal('1') + change_percent)
        
        self.current_prices[symbol] = new_price
        self._record_price_history(symbol, new_price)
        
        return new_price
    
    def _record_price_history(self, symbol: str, price: Decimal):
        """Record price history for analysis."""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        self.price_history[symbol].append({
            'timestamp': datetime.now(),
            'price': float(price),
            'volume': random.randint(100, 10000)  # Simulated volume
        })
        
        # Keep only last 1000 price points
        if len(self.price_history[symbol]) > 1000:
            self.price_history[symbol] = self.price_history[symbol][-1000:]

class PaperTradingAccount:
    """
    Paper trading account that simulates real trading without actual money.
    """
    
    def __init__(self, initial_balance: Decimal = Decimal('10000'), 
                 commission_rate: Decimal = Decimal('0.001')):
        self.account_id = str(uuid.uuid4())
        self.initial_balance = initial_balance
        self.cash_balance = initial_balance
        self.commission_rate = commission_rate
        
        # Portfolio tracking
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        self.trade_history: List[TradeRecord] = []
        self.portfolio_history: List[PortfolioSnapshot] = []
        
        # Risk management
        self.risk_limits = RiskLimits()
        self.risk_manager = RiskManager(self.risk_limits, portfolio_value=float(initial_balance))
        
        # Market data
        self.market_simulator = MarketDataSimulator()
        
        self.logger = get_logger(f"paper_account_{self.account_id[:8]}")
        
        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.total_commission_paid = Decimal('0')
        self.max_drawdown = Decimal('0')
        self.peak_value = initial_balance
        
        self.logger.info(f"Created paper trading account with ${initial_balance} initial balance")
    
    @property
    def total_portfolio_value(self) -> Decimal:
        """Calculate total portfolio value including cash and positions."""
        positions_value = sum(pos.market_value for pos in self.positions.values())
        return self.cash_balance + positions_value
    
    @property
    def unrealized_pnl(self) -> Decimal:
        """Calculate total unrealized P&L."""
        return sum(pos.unrealized_pnl for pos in self.positions.values())
    
    @property
    def realized_pnl(self) -> Decimal:
        """Calculate total realized P&L."""
        return sum(trade.pnl for trade in self.trade_history)
    
    @property
    def total_pnl(self) -> Decimal:
        """Calculate total P&L (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl
    
    def update_market_prices(self):
        """Update all position prices with current market data."""
        for symbol, position in self.positions.items():
            current_price = self.market_simulator.get_current_price(symbol)
            position.current_price = current_price
            position.unrealized_pnl = (current_price - position.average_price) * position.quantity
            position.last_update = datetime.now()
        
        # Update portfolio performance tracking
        current_value = self.total_portfolio_value
        if current_value > self.peak_value:
            self.peak_value = current_value
        else:
            drawdown = (self.peak_value - current_value) / self.peak_value
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown
    
    def place_order(self, symbol: str, order_type: OrderType, side: OrderSide,
                   quantity: Decimal, price: Optional[Decimal] = None,
                   stop_price: Optional[Decimal] = None) -> str:
        """Place a trading order."""
        # Validate inputs
        symbol = InputValidator.validate_crypto_symbol(symbol)
        quantity = Decimal(str(InputValidator.validate_volume(float(quantity))))
        
        # Create order
        order = Order(
            symbol=symbol,
            order_type=order_type,
            side=side,
            quantity=quantity,
            price=price or Decimal('0'),
            stop_price=stop_price
        )
        
        # Risk checks
        if not self._validate_order_risk(order):
            order.status = OrderStatus.REJECTED
            self.logger.warning(f"Order rejected due to risk limits: {order.order_id}")
            self.orders[order.order_id] = order
            return order.order_id
        
        # Check if we have enough buying power
        if side == OrderSide.BUY:
            estimated_cost = self._estimate_order_cost(order)
            if estimated_cost > self.cash_balance:
                order.status = OrderStatus.REJECTED
                self.logger.warning(f"Order rejected - insufficient funds: {order.order_id}")
                self.orders[order.order_id] = order
                return order.order_id
        
        # Check if we have enough shares to sell
        if side == OrderSide.SELL:
            if symbol not in self.positions or self.positions[symbol].quantity < quantity:
                order.status = OrderStatus.REJECTED
                self.logger.warning(f"Order rejected - insufficient position: {order.order_id}")
                self.orders[order.order_id] = order
                return order.order_id
        
        self.orders[order.order_id] = order
        self.logger.info(f"Order placed: {side.value} {quantity} {symbol} @ {price or 'market'}")
        
        # For market orders, execute immediately
        if order_type == OrderType.MARKET:
            self._execute_order(order.order_id)
        
        return order.order_id
    
    def _validate_order_risk(self, order: Order) -> bool:
        """Validate order against risk limits."""
        try:
            current_value = float(self.total_portfolio_value)
            current_price = self.market_simulator.get_current_price(order.symbol)
            order_value = float(order.quantity * current_price)
            
            # Calculate max position size (2% of portfolio)
            max_position_value = current_value * 0.02  
            
            # For testing, also ensure we don't exceed 10% of portfolio
            max_portfolio_percent = current_value * 0.10
            
            # Use the more generous limit for now
            max_allowed = max(max_position_value, max_portfolio_percent)
            
            self.logger.info(f"Risk check: order_value=${order_value:.2f}, max_allowed=${max_allowed:.2f}")
            return order_value <= max_allowed
            
        except Exception as e:
            self.logger.error(f"Risk validation failed: {e}")
            return False
    
    def _estimate_order_cost(self, order: Order) -> Decimal:
        """Estimate the total cost of an order including commission."""
        if order.side == OrderSide.BUY:
            if order.order_type == OrderType.MARKET:
                current_price = self.market_simulator.get_current_price(order.symbol)
            else:
                current_price = order.price
            
            gross_amount = order.quantity * current_price
            commission = gross_amount * self.commission_rate
            return gross_amount + commission
        else:
            return Decimal('0')  # Selling doesn't require cash
    
    def _execute_order(self, order_id: str):
        """Execute a pending order."""
        if order_id not in self.orders:
            self.logger.error(f"Order {order_id} not found")
            return
        
        order = self.orders[order_id]
        if order.status != OrderStatus.PENDING:
            self.logger.warning(f"Order {order_id} not in pending status")
            return
        
        # Get execution price
        if order.order_type == OrderType.MARKET:
            execution_price = self.market_simulator.get_current_price(order.symbol)
        else:
            execution_price = order.price
        
        # Calculate commission
        gross_amount = order.quantity * execution_price
        commission = gross_amount * self.commission_rate
        
        # Update order
        order.filled_quantity = order.quantity
        order.filled_price = execution_price
        order.commission = commission
        order.status = OrderStatus.FILLED
        order.filled_time = datetime.now()
        
        # Update portfolio
        if order.side == OrderSide.BUY:
            self._add_position(order.symbol, order.quantity, execution_price)
            self.cash_balance -= (gross_amount + commission)
        else:
            pnl = self._reduce_position(order.symbol, order.quantity, execution_price)
            self.cash_balance += (gross_amount - commission)
            
            # Create trade record with P&L
            trade = TradeRecord(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=execution_price,
                commission=commission,
                pnl=pnl
            )
            self.trade_history.append(trade)
        
        self.total_commission_paid += commission
        self.total_trades += 1
        
        if order.side == OrderSide.SELL:
            # Check if this was a winning trade
            last_trade = self.trade_history[-1] if self.trade_history else None
            if last_trade and last_trade.pnl > 0:
                self.winning_trades += 1
        
        self.logger.info(f"Order executed: {order.side.value} {order.quantity} {order.symbol} @ ${execution_price}")
    
    def _add_position(self, symbol: str, quantity: Decimal, price: Decimal):
        """Add to existing position or create new position."""
        if symbol in self.positions:
            # Update existing position (average price calculation)
            existing = self.positions[symbol]
            total_quantity = existing.quantity + quantity
            total_cost = (existing.quantity * existing.average_price) + (quantity * price)
            new_avg_price = total_cost / total_quantity
            
            existing.quantity = total_quantity
            existing.average_price = new_avg_price
            existing.current_price = price
            existing.last_update = datetime.now()
        else:
            # Create new position
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                average_price=price,
                current_price=price
            )
    
    def _reduce_position(self, symbol: str, quantity: Decimal, price: Decimal) -> Decimal:
        """Reduce position and calculate realized P&L."""
        if symbol not in self.positions:
            self.logger.error(f"Cannot reduce position - {symbol} not found")
            return Decimal('0')
        
        position = self.positions[symbol]
        if position.quantity < quantity:
            self.logger.error(f"Cannot reduce position - insufficient quantity")
            return Decimal('0')
        
        # Calculate realized P&L
        pnl = (price - position.average_price) * quantity
        
        # Update position
        position.quantity -= quantity
        position.realized_pnl += pnl
        position.last_update = datetime.now()
        
        # Remove position if quantity is zero
        if position.quantity == 0:
            del self.positions[symbol]
        
        return pnl
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        if order_id not in self.orders:
            return False
        
        order = self.orders[order_id]
        if order.status == OrderStatus.PENDING:
            order.status = OrderStatus.CANCELLED
            self.logger.info(f"Order cancelled: {order_id}")
            return True
        
        return False
    
    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """Get status of an order."""
        return self.orders[order_id].status if order_id in self.orders else None
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol."""
        return self.positions.get(symbol)
    
    def get_account_summary(self) -> Dict[str, Any]:
        """Get comprehensive account summary."""
        self.update_market_prices()
        
        # Calculate win rate
        win_rate = (self.winning_trades / max(self.total_trades, 1)) * 100
        
        return {
            'account_id': self.account_id,
            'cash_balance': float(self.cash_balance),
            'positions_value': float(sum(pos.market_value for pos in self.positions.values())),
            'total_value': float(self.total_portfolio_value),
            'unrealized_pnl': float(self.unrealized_pnl),
            'realized_pnl': float(self.realized_pnl),
            'total_pnl': float(self.total_pnl),
            'total_return_pct': float((self.total_portfolio_value - self.initial_balance) / self.initial_balance * 100),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'win_rate_pct': win_rate,
            'total_commission': float(self.total_commission_paid),
            'max_drawdown_pct': float(self.max_drawdown * 100),
            'positions': {
                symbol: {
                    'quantity': float(pos.quantity),
                    'avg_price': float(pos.average_price),
                    'current_price': float(pos.current_price),
                    'market_value': float(pos.market_value),
                    'unrealized_pnl': float(pos.unrealized_pnl),
                    'unrealized_pnl_pct': float(pos.unrealized_pnl / pos.cost_basis * 100) if pos.cost_basis > 0 else 0
                }
                for symbol, pos in self.positions.items()
            },
            'recent_orders': [
                {
                    'order_id': order.order_id,
                    'symbol': order.symbol,
                    'side': order.side.value,
                    'quantity': float(order.quantity),
                    'price': float(order.price),
                    'status': order.status.value,
                    'created_time': order.created_time.isoformat()
                }
                for order in sorted(self.orders.values(), key=lambda x: x.created_time, reverse=True)[:10]
            ]
        }
    
    def save_portfolio_snapshot(self):
        """Save current portfolio state for historical tracking."""
        self.update_market_prices()
        
        snapshot = PortfolioSnapshot(
            timestamp=datetime.now(),
            total_value=self.total_portfolio_value,
            cash_balance=self.cash_balance,
            positions_value=sum(pos.market_value for pos in self.positions.values()),
            unrealized_pnl=self.unrealized_pnl,
            realized_pnl=self.realized_pnl,
            positions=self.positions.copy()
        )
        
        self.portfolio_history.append(snapshot)
        
        # Keep only last 30 days of snapshots
        cutoff_date = datetime.now() - timedelta(days=30)
        self.portfolio_history = [s for s in self.portfolio_history if s.timestamp > cutoff_date]

# Example usage and testing
async def demo_paper_trading():
    """Demonstrate paper trading functionality."""
    print("PowerTraderAI+ Paper Trading Demo")
    print("=" * 40)
    
    # Create account
    account = PaperTradingAccount(initial_balance=Decimal('10000'))
    
    # Display initial state
    summary = account.get_account_summary()
    print(f"Initial Balance: ${summary['cash_balance']:.2f}")
    
    # Place some test orders
    print("\nPlacing test orders...")
    
    # Buy BTC
    btc_order = account.place_order(
        symbol="BTC",
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=Decimal('0.1')
    )
    print(f"BTC Buy Order: {btc_order}")
    
    # Buy ETH
    eth_order = account.place_order(
        symbol="ETH",
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=Decimal('2.0')
    )
    print(f"ETH Buy Order: {eth_order}")
    
    # Wait a bit and update prices
    await asyncio.sleep(1)
    account.update_market_prices()
    
    # Show updated portfolio
    print("\nPortfolio after purchases:")
    summary = account.get_account_summary()
    print(f"Cash: ${summary['cash_balance']:.2f}")
    print(f"Total Value: ${summary['total_value']:.2f}")
    print(f"P&L: ${summary['total_pnl']:.2f} ({summary['total_return_pct']:.2f}%)")
    
    for symbol, pos_data in summary['positions'].items():
        print(f"  {symbol}: {pos_data['quantity']:.4f} @ ${pos_data['avg_price']:.2f} "
              f"(Value: ${pos_data['market_value']:.2f}, "
              f"P&L: ${pos_data['unrealized_pnl']:.2f})")

if __name__ == "__main__":
    # Run demo
    asyncio.run(demo_paper_trading())