"""
PowerTraderAI+ Risk Management System

Implements comprehensive risk controls, monitoring, and emergency procedures
for financial trading operations.
"""

import logging
import time
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json

# Risk alert levels
class RiskLevel(Enum):
    LOW = "low"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

# Risk event types
class RiskEventType(Enum):
    PORTFOLIO_DRAWDOWN = "portfolio_drawdown"
    POSITION_CONCENTRATION = "position_concentration"
    VOLATILITY_SPIKE = "volatility_spike"
    API_FAILURE = "api_failure"
    SYSTEM_ERROR = "system_error"
    MARGIN_CALL = "margin_call"

@dataclass
class RiskLimits:
    """Portfolio and position risk limits configuration"""
    
    # Portfolio level limits (as percentages)
    max_daily_loss: float = 0.02      # 2% max daily loss
    max_weekly_loss: float = 0.05     # 5% max weekly loss  
    max_monthly_loss: float = 0.10    # 10% max monthly loss
    max_annual_loss: float = 0.20     # 20% max annual loss
    
    # Position level limits
    max_position_size: float = 0.10   # 10% max single position
    max_sector_exposure: float = 0.25 # 25% max sector exposure
    max_correlation_exposure: float = 0.15  # 15% max correlated positions
    
    # Strategy level limits
    max_strategy_allocation: float = 0.30    # 30% max per strategy
    min_strategy_performance: float = -0.05  # -5% strategy disable threshold
    max_consecutive_losses: int = 5          # Max consecutive losses
    
    # Volatility and leverage limits
    max_volatility_threshold: float = 0.40  # 40% volatility emergency stop
    max_leverage: float = 2.0               # 2x maximum leverage

@dataclass
class RiskAlert:
    """Risk alert data structure"""
    timestamp: datetime
    level: RiskLevel
    event_type: RiskEventType
    message: str
    current_value: float
    threshold: float
    portfolio_value: Optional[float] = None
    position_details: Optional[Dict] = None

@dataclass
class PortfolioMetrics:
    """Real-time portfolio risk metrics"""
    total_value: float
    daily_pnl: float
    weekly_pnl: float
    monthly_pnl: float
    annual_pnl: float
    volatility: float
    max_drawdown: float
    sharpe_ratio: float
    positions: Dict[str, float] = field(default_factory=dict)
    correlations: Dict[str, float] = field(default_factory=dict)

class RiskManager:
    """
    Comprehensive risk management system for PowerTraderAI+
    
    Monitors portfolio metrics, enforces risk limits, and executes
    emergency procedures when thresholds are breached.
    """
    
    def __init__(self, limits: RiskLimits, portfolio_value: float = 0.0):
        self.limits = limits
        self.portfolio_value = portfolio_value
        self.alerts: List[RiskAlert] = []
        self.is_trading_halted = False
        self.emergency_stop_triggered = False
        
        # Risk thresholds for different alert levels
        self.risk_thresholds = {
            'portfolio_drawdown': {
                'warning': 0.03,    # 3% drawdown warning
                'critical': 0.05,   # 5% drawdown critical
                'emergency': 0.08   # 8% emergency stop
            },
            'volatility': {
                'warning': 0.25,    # 25% volatility warning
                'critical': 0.40,   # 40% critical
                'emergency': 0.60   # 60% emergency stop
            },
            'leverage': {
                'warning': 1.5,     # 1.5x leverage warning
                'critical': 2.0,    # 2x critical
                'emergency': 2.5    # 2.5x emergency stop
            }
        }
        
        # Monitoring thread
        self._monitoring_active = False
        self._monitoring_thread = None
        
        # Logger
        self.logger = logging.getLogger(__name__)
        
    def start_monitoring(self):
        """Start real-time risk monitoring"""
        if self._monitoring_active:
            return
            
        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(target=self._monitor_risk_loop)
        self._monitoring_thread.daemon = True
        self._monitoring_thread.start()
        self.logger.info("Risk monitoring started")
        
    def stop_monitoring(self):
        """Stop risk monitoring"""
        self._monitoring_active = False
        if self._monitoring_thread:
            self._monitoring_thread.join()
        self.logger.info("Risk monitoring stopped")
        
    def _monitor_risk_loop(self):
        """Main risk monitoring loop"""
        while self._monitoring_active:
            try:
                # Get current portfolio metrics
                metrics = self.get_portfolio_metrics()
                
                # Check all risk conditions
                self._check_portfolio_risk(metrics)
                self._check_position_risk(metrics)
                self._check_volatility_risk(metrics)
                
                # Sleep for monitoring interval
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                self.logger.error(f"Risk monitoring error: {e}")
                time.sleep(10)  # Longer sleep on error
                
    def get_portfolio_metrics(self) -> PortfolioMetrics:
        """
        Get current portfolio metrics for risk assessment
        
        In production, this would fetch real portfolio data.
        This is a mock implementation for demonstration.
        """
        # Mock portfolio metrics - replace with real implementation
        return PortfolioMetrics(
            total_value=self.portfolio_value,
            daily_pnl=0.0,
            weekly_pnl=0.0,
            monthly_pnl=0.0,
            annual_pnl=0.0,
            volatility=0.15,
            max_drawdown=0.02,
            sharpe_ratio=1.5,
            positions={'BTC': 0.3, 'ETH': 0.2, 'STOCKS': 0.5},
            correlations={'BTC_ETH': 0.7}
        )
        
    def _check_portfolio_risk(self, metrics: PortfolioMetrics):
        """Check portfolio-level risk metrics"""
        
        # Check daily loss limit
        if metrics.daily_pnl < 0:
            daily_loss_pct = abs(metrics.daily_pnl) / metrics.total_value
            
            if daily_loss_pct >= self.limits.max_daily_loss:
                self._trigger_alert(
                    RiskLevel.EMERGENCY,
                    RiskEventType.PORTFOLIO_DRAWDOWN,
                    f"Daily loss limit exceeded: {daily_loss_pct:.2%}",
                    daily_loss_pct,
                    self.limits.max_daily_loss
                )
                self.emergency_stop()
                
            elif daily_loss_pct >= self.risk_thresholds['portfolio_drawdown']['critical']:
                self._trigger_alert(
                    RiskLevel.CRITICAL,
                    RiskEventType.PORTFOLIO_DRAWDOWN,
                    f"Critical daily loss: {daily_loss_pct:.2%}",
                    daily_loss_pct,
                    self.risk_thresholds['portfolio_drawdown']['critical']
                )
                
            elif daily_loss_pct >= self.risk_thresholds['portfolio_drawdown']['warning']:
                self._trigger_alert(
                    RiskLevel.WARNING,
                    RiskEventType.PORTFOLIO_DRAWDOWN,
                    f"Daily loss warning: {daily_loss_pct:.2%}",
                    daily_loss_pct,
                    self.risk_thresholds['portfolio_drawdown']['warning']
                )
    
    def _check_position_risk(self, metrics: PortfolioMetrics):
        """Check position concentration and correlation risks"""
        
        for symbol, position_pct in metrics.positions.items():
            if position_pct > self.limits.max_position_size:
                self._trigger_alert(
                    RiskLevel.CRITICAL,
                    RiskEventType.POSITION_CONCENTRATION,
                    f"Position size limit exceeded for {symbol}: {position_pct:.2%}",
                    position_pct,
                    self.limits.max_position_size,
                    position_details={'symbol': symbol, 'size': position_pct}
                )
                
    def _check_volatility_risk(self, metrics: PortfolioMetrics):
        """Check volatility risk levels"""
        
        if metrics.volatility >= self.risk_thresholds['volatility']['emergency']:
            self._trigger_alert(
                RiskLevel.EMERGENCY,
                RiskEventType.VOLATILITY_SPIKE,
                f"Extreme volatility detected: {metrics.volatility:.2%}",
                metrics.volatility,
                self.risk_thresholds['volatility']['emergency']
            )
            self.emergency_stop()
            
        elif metrics.volatility >= self.risk_thresholds['volatility']['critical']:
            self._trigger_alert(
                RiskLevel.CRITICAL,
                RiskEventType.VOLATILITY_SPIKE,
                f"High volatility warning: {metrics.volatility:.2%}",
                metrics.volatility,
                self.risk_thresholds['volatility']['critical']
            )
            
    def _trigger_alert(self, level: RiskLevel, event_type: RiskEventType, 
                      message: str, current_value: float, threshold: float,
                      position_details: Optional[Dict] = None):
        """Trigger a risk alert and execute appropriate response"""
        
        alert = RiskAlert(
            timestamp=datetime.now(),
            level=level,
            event_type=event_type,
            message=message,
            current_value=current_value,
            threshold=threshold,
            portfolio_value=self.portfolio_value,
            position_details=position_details
        )
        
        self.alerts.append(alert)
        
        # Log the alert
        log_level = {
            RiskLevel.LOW: logging.INFO,
            RiskLevel.WARNING: logging.WARNING,
            RiskLevel.CRITICAL: logging.ERROR,
            RiskLevel.EMERGENCY: logging.CRITICAL
        }[level]
        
        self.logger.log(log_level, f"RISK ALERT [{level.value.upper()}]: {message}")
        
        # Execute response based on alert level
        if level == RiskLevel.WARNING:
            self._handle_warning_alert(alert)
        elif level == RiskLevel.CRITICAL:
            self._handle_critical_alert(alert)
        elif level == RiskLevel.EMERGENCY:
            self._handle_emergency_alert(alert)
            
    def _handle_warning_alert(self, alert: RiskAlert):
        """Handle warning level alerts"""
        # Reduce position sizes by 25%
        # Increase stop-loss sensitivity
        # Send notifications
        self.logger.info("Executing warning level response")
        
    def _handle_critical_alert(self, alert: RiskAlert):
        """Handle critical level alerts"""
        # Halt new position openings
        # Reduce existing positions by 50%
        # Require manual approval for trades
        self.is_trading_halted = True
        self.logger.warning("Trading halted due to critical risk level")
        
    def _handle_emergency_alert(self, alert: RiskAlert):
        """Handle emergency level alerts"""
        self.emergency_stop()
        
    def emergency_stop(self):
        """
        Execute emergency stop procedures
        
        STOP ALL TRADING IMMEDIATELY and preserve system state
        """
        if self.emergency_stop_triggered:
            return  # Already triggered
            
        self.emergency_stop_triggered = True
        self.is_trading_halted = True
        
        self.logger.critical("EMERGENCY STOP ACTIVATED")
        
        try:
            # 1. Stop all trading strategies
            self._halt_all_strategies()
            
            # 2. Cancel all pending orders
            self._cancel_all_pending_orders()
            
            # 3. Close all positions at market price
            self._close_all_positions()
            
            # 4. Disconnect from APIs
            self._disconnect_apis()
            
            # 5. Save system state
            self._save_emergency_snapshot()
            
            # 6. Send emergency notifications
            self._send_emergency_notifications()
            
        except Exception as e:
            self.logger.critical(f"Emergency stop procedure failed: {e}")
            
    def _halt_all_strategies(self):
        """Stop all trading strategies"""
        self.logger.info("Halting all trading strategies")
        # Implementation would interact with strategy manager
        
    def _cancel_all_pending_orders(self):
        """Cancel all pending orders"""
        self.logger.info("Cancelling all pending orders")
        # Implementation would interact with order management system
        
    def _close_all_positions(self):
        """Close all open positions"""
        self.logger.info("Closing all positions")
        # Implementation would interact with position management system
        
    def _disconnect_apis(self):
        """Disconnect from all trading APIs"""
        self.logger.info("Disconnecting from all APIs")
        # Implementation would disconnect API connections
        
    def _save_emergency_snapshot(self):
        """Save current system state for analysis"""
        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'portfolio_value': self.portfolio_value,
            'alerts': [self._alert_to_dict(alert) for alert in self.alerts[-10:]],
            'emergency_trigger': 'automatic_risk_management'
        }
        
        try:
            with open(f'emergency_snapshot_{int(time.time())}.json', 'w') as f:
                json.dump(snapshot, f, indent=2)
            self.logger.info("Emergency snapshot saved")
        except Exception as e:
            self.logger.error(f"Failed to save emergency snapshot: {e}")
            
    def _send_emergency_notifications(self):
        """Send emergency notifications to administrators"""
        self.logger.critical("Emergency notifications sent")
        # Implementation would send SMS/email/Slack notifications
        
    def _alert_to_dict(self, alert: RiskAlert) -> Dict:
        """Convert alert to dictionary for serialization"""
        return {
            'timestamp': alert.timestamp.isoformat(),
            'level': alert.level.value,
            'event_type': alert.event_type.value,
            'message': alert.message,
            'current_value': alert.current_value,
            'threshold': alert.threshold,
            'portfolio_value': alert.portfolio_value,
            'position_details': alert.position_details
        }
        
    def calculate_position_size(self, account_value: float, 
                              risk_per_trade: float = 0.01) -> float:
        """
        Calculate optimal position size based on risk management rules
        
        Args:
            account_value: Current account value
            risk_per_trade: Risk percentage per trade (default 1%)
            
        Returns:
            Maximum position size in dollars
        """
        # Base risk amount
        max_risk_amount = account_value * risk_per_trade
        
        # Apply position size limit
        max_position = account_value * self.limits.max_position_size
        
        # Apply daily loss budget remaining
        daily_loss_budget = account_value * self.limits.max_daily_loss
        
        # Return the most conservative limit
        return min(max_risk_amount, max_position, daily_loss_budget)
        
    def validate_trade(self, symbol: str, quantity: float, 
                      price: float) -> Tuple[bool, str]:
        """
        Validate a proposed trade against risk limits
        
        Returns:
            (is_valid, reason) tuple
        """
        if self.is_trading_halted:
            return False, "Trading is currently halted due to risk controls"
            
        if self.emergency_stop_triggered:
            return False, "Emergency stop is active - no trading allowed"
            
        trade_value = quantity * price
        
        # Check position size limit
        if trade_value > self.calculate_position_size(self.portfolio_value):
            return False, f"Trade size exceeds risk limits: ${trade_value:,.2f}"
            
        return True, "Trade approved"
        
    def get_risk_summary(self) -> Dict:
        """Get current risk status summary"""
        recent_alerts = [a for a in self.alerts if 
                        (datetime.now() - a.timestamp).total_seconds() < 3600]
        
        return {
            'is_trading_halted': self.is_trading_halted,
            'emergency_stop_triggered': self.emergency_stop_triggered,
            'recent_alerts_count': len(recent_alerts),
            'highest_recent_alert': max([a.level.value for a in recent_alerts], default='none'),
            'portfolio_value': self.portfolio_value,
            'risk_limits': {
                'max_daily_loss': self.limits.max_daily_loss,
                'max_position_size': self.limits.max_position_size,
                'max_leverage': self.limits.max_leverage
            }
        }
        
    def reset_emergency_stop(self, manual_override: bool = False):
        """
        Reset emergency stop (use with extreme caution)
        
        Args:
            manual_override: Requires explicit confirmation for safety
        """
        if not manual_override:
            raise ValueError("Emergency stop reset requires manual_override=True")
            
        self.emergency_stop_triggered = False
        self.is_trading_halted = False
        self.logger.warning("Emergency stop reset - trading re-enabled")

# Example usage and configuration
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Create risk manager with custom limits
    limits = RiskLimits(
        max_daily_loss=0.02,        # 2% max daily loss
        max_position_size=0.05,     # 5% max position size
        max_leverage=1.5            # 1.5x max leverage
    )
    
    risk_manager = RiskManager(limits, portfolio_value=100000)
    
    # Start monitoring
    risk_manager.start_monitoring()
    
    # Example trade validation
    is_valid, reason = risk_manager.validate_trade("BTC", 0.1, 50000)
    print(f"Trade validation: {is_valid} - {reason}")
    
    # Get risk summary
    summary = risk_manager.get_risk_summary()
    print(f"Risk summary: {summary}")
    
    # Stop monitoring
    time.sleep(2)
    risk_manager.stop_monitoring()