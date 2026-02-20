"""
PowerTrader AI Live Monitoring System

Real-time monitoring and alerting system for live trading operations.
Tracks performance, risk metrics, and system health.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
import threading
import queue
from pathlib import Path
import sys
import os
try:
    import smtplib
    from email.mime.text import MimeText
    from email.mime.multipart import MimeMultipart
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False
    print("Email functionality not available")

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

# PowerTrader imports
from pt_risk import RiskManager, RiskLimits
from pt_performance import PerformanceMonitor
from pt_paper_trading import PaperTradingAccount
from pt_logging import get_logger

@dataclass
class AlertLevel:
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning" 
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class Alert:
    """System alert data."""
    alert_id: str
    level: str
    component: str
    message: str
    details: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    
@dataclass
class MonitoringMetric:
    """Monitoring metric data."""
    name: str
    value: float
    unit: str
    threshold_low: Optional[float] = None
    threshold_high: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def is_within_bounds(self) -> bool:
        """Check if metric is within acceptable bounds."""
        if self.threshold_low is not None and self.value < self.threshold_low:
            return False
        if self.threshold_high is not None and self.value > self.threshold_high:
            return False
        return True

@dataclass
class SystemHealth:
    """Overall system health status."""
    status: str  # 'healthy', 'warning', 'critical'
    components: Dict[str, bool]
    metrics: Dict[str, float]
    alerts_count: Dict[str, int]
    uptime_seconds: float
    last_check: datetime = field(default_factory=datetime.now)

class LiveMonitor:
    """
    Live monitoring system for PowerTrader AI.
    Tracks system performance, trading metrics, and generates alerts.
    """
    
    def __init__(self, config_path: str = "config/monitoring.json"):
        self.config_path = config_path
        self.logger = get_logger("live_monitor")
        self.config = self._load_config()
        
        # Monitoring state
        self.start_time = datetime.now()
        self.is_running = False
        self.monitor_thread = None
        
        # Metrics and alerts
        self.metrics: Dict[str, List[MonitoringMetric]] = {}
        self.alerts: List[Alert] = []
        self.alert_queue = queue.Queue()
        
        # Performance monitoring
        self.performance_monitor = PerformanceMonitor(enable_system_metrics=True)
        
        # Component references
        self.paper_account: Optional[PaperTradingAccount] = None
        self.risk_manager: Optional[RiskManager] = None
        
        # Alert handlers
        self.alert_handlers: List[Callable[[Alert], None]] = []
        
        # Thresholds from config
        self.thresholds = self.config.get("thresholds", {})
        
        self.logger.info("Live monitoring system initialized")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load monitoring configuration."""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            else:
                # Default configuration
                default_config = {
                    "monitoring_interval": 5,
                    "metrics_retention_hours": 24,
                    "alerts_retention_days": 7,
                    "thresholds": {
                        "max_drawdown_pct": 5.0,
                        "max_daily_loss": 1000.0,
                        "min_available_balance_pct": 10.0,
                        "max_position_size_pct": 20.0,
                        "max_memory_usage_mb": 512,
                        "max_cpu_usage_pct": 80,
                        "max_response_time_ms": 5000
                    },
                    "alerts": {
                        "enable_email": False,
                        "enable_console": True,
                        "enable_file": True,
                        "email_recipients": [],
                        "smtp_settings": {
                            "server": "smtp.gmail.com",
                            "port": 587,
                            "username": "",
                            "password": ""
                        }
                    }
                }
                self._save_config(default_config)
                return default_config
        except Exception as e:
            self.logger.error(f"Failed to load monitoring config: {e}")
            return {}
    
    def _save_config(self, config: Dict[str, Any]):
        """Save configuration to file."""
        try:
            Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
    
    def register_paper_account(self, account: PaperTradingAccount):
        """Register paper trading account for monitoring."""
        self.paper_account = account
        self.logger.info(f"Registered paper trading account: {account.account_id}")
    
    def register_risk_manager(self, risk_manager: RiskManager):
        """Register risk manager for monitoring."""
        self.risk_manager = risk_manager
        self.logger.info("Registered risk manager for monitoring")
    
    def add_alert_handler(self, handler: Callable[[Alert], None]):
        """Add custom alert handler."""
        self.alert_handlers.append(handler)
    
    def start_monitoring(self):
        """Start the monitoring system."""
        if self.is_running:
            self.logger.warning("Monitoring is already running")
            return
        
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        # Start alert processing
        alert_thread = threading.Thread(target=self._alert_processing_loop, daemon=True)
        alert_thread.start()
        
        self.logger.info("Live monitoring started")
    
    def stop_monitoring(self):
        """Stop the monitoring system."""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self.logger.info("Live monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop."""
        interval = self.config.get("monitoring_interval", 5)
        
        while self.is_running:
            try:
                self._collect_metrics()
                self._check_thresholds()
                self._cleanup_old_data()
                time.sleep(interval)
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(interval)
    
    def _alert_processing_loop(self):
        """Process alerts in background thread."""
        while self.is_running:
            try:
                alert = self.alert_queue.get(timeout=1)
                self._handle_alert(alert)
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error processing alert: {e}")
    
    def _collect_metrics(self):
        """Collect system and trading metrics."""
        timestamp = datetime.now()
        
        # System metrics
        try:
            import psutil
            
            # Memory usage
            memory = psutil.virtual_memory()
            self._add_metric("memory_usage_mb", memory.used / 1024 / 1024, "MB",
                           threshold_high=self.thresholds.get("max_memory_usage_mb", 512))
            
            self._add_metric("memory_usage_pct", memory.percent, "%",
                           threshold_high=85.0)
            
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self._add_metric("cpu_usage_pct", cpu_percent, "%",
                           threshold_high=self.thresholds.get("max_cpu_usage_pct", 80))
            
            # Disk usage
            disk = psutil.disk_usage('/')
            self._add_metric("disk_usage_pct", disk.percent, "%",
                           threshold_high=90.0)
            
        except ImportError:
            # psutil not available, skip system metrics
            pass
        except Exception as e:
            self.logger.error(f"Failed to collect system metrics: {e}")
        
        # Trading metrics (if paper account available)
        if self.paper_account:
            try:
                self.paper_account.update_market_prices()
                summary = self.paper_account.get_account_summary()
                
                # Portfolio value
                self._add_metric("portfolio_value", summary["total_value"], "USD")
                
                # P&L metrics
                self._add_metric("total_pnl", summary["total_pnl"], "USD")
                self._add_metric("unrealized_pnl", summary["unrealized_pnl"], "USD")
                self._add_metric("realized_pnl", summary["realized_pnl"], "USD")
                
                # Return percentage
                return_pct = summary["total_return_pct"]
                self._add_metric("total_return_pct", return_pct, "%")
                
                # Drawdown check
                if return_pct < -self.thresholds.get("max_drawdown_pct", 5.0):
                    self._create_alert(AlertLevel.WARNING, "Portfolio",
                                     f"Portfolio drawdown exceeded threshold: {return_pct:.2f}%",
                                     {"return_pct": return_pct, "threshold": -self.thresholds.get("max_drawdown_pct", 5.0)})
                
                # Cash balance check
                cash_pct = (summary["cash_balance"] / summary["total_value"]) * 100
                self._add_metric("cash_balance_pct", cash_pct, "%",
                               threshold_low=self.thresholds.get("min_available_balance_pct", 10.0))
                
                # Win rate
                self._add_metric("win_rate_pct", summary["win_rate_pct"], "%")
                
                # Total trades
                self._add_metric("total_trades", summary["total_trades"], "count")
                
            except Exception as e:
                self.logger.error(f"Failed to collect trading metrics: {e}")
        
        # Performance metrics from performance monitor
        try:
            perf_summary = self.performance_monitor.get_summary()
            if 'timers' in perf_summary:
                for timer_name, timer_data in perf_summary['timers'].items():
                    if 'average_ms' in timer_data:
                        self._add_metric(f"timer_{timer_name}_ms", timer_data['average_ms'], "ms",
                                       threshold_high=self.thresholds.get("max_response_time_ms", 5000))
        except Exception as e:
            self.logger.error(f"Failed to collect performance metrics: {e}")
    
    def _add_metric(self, name: str, value: float, unit: str,
                   threshold_low: Optional[float] = None,
                   threshold_high: Optional[float] = None):
        """Add a metric measurement."""
        metric = MonitoringMetric(
            name=name,
            value=value,
            unit=unit,
            threshold_low=threshold_low,
            threshold_high=threshold_high
        )
        
        if name not in self.metrics:
            self.metrics[name] = []
        
        self.metrics[name].append(metric)
        
        # Clean up old metrics
        retention_hours = self.config.get("metrics_retention_hours", 24)
        cutoff_time = datetime.now() - timedelta(hours=retention_hours)
        self.metrics[name] = [m for m in self.metrics[name] if m.timestamp > cutoff_time]
    
    def _check_thresholds(self):
        """Check if any metrics exceed their thresholds."""
        for metric_name, metric_list in self.metrics.items():
            if not metric_list:
                continue
            
            latest_metric = metric_list[-1]
            
            if not latest_metric.is_within_bounds:
                alert_level = AlertLevel.WARNING
                
                # Determine alert severity
                if "critical" in metric_name.lower() or latest_metric.value < 0:
                    alert_level = AlertLevel.CRITICAL
                elif "error" in metric_name.lower():
                    alert_level = AlertLevel.ERROR
                
                # Create threshold alert
                if latest_metric.threshold_high and latest_metric.value > latest_metric.threshold_high:
                    message = f"{metric_name} exceeded high threshold: {latest_metric.value:.2f} {latest_metric.unit} > {latest_metric.threshold_high} {latest_metric.unit}"
                elif latest_metric.threshold_low and latest_metric.value < latest_metric.threshold_low:
                    message = f"{metric_name} below low threshold: {latest_metric.value:.2f} {latest_metric.unit} < {latest_metric.threshold_low} {latest_metric.unit}"
                else:
                    continue
                
                self._create_alert(alert_level, "Metrics", message, {
                    "metric_name": metric_name,
                    "value": latest_metric.value,
                    "unit": latest_metric.unit,
                    "threshold_low": latest_metric.threshold_low,
                    "threshold_high": latest_metric.threshold_high
                })
    
    def _create_alert(self, level: str, component: str, message: str, details: Dict[str, Any]):
        """Create and queue an alert."""
        alert_id = f"{int(time.time())}_{len(self.alerts)}"
        
        alert = Alert(
            alert_id=alert_id,
            level=level,
            component=component,
            message=message,
            details=details
        )
        
        self.alerts.append(alert)
        self.alert_queue.put(alert)
    
    def _handle_alert(self, alert: Alert):
        """Handle an alert by routing to configured handlers."""
        # Console output (if enabled)
        if self.config.get("alerts", {}).get("enable_console", True):
            color_codes = {
                AlertLevel.INFO: "\033[94m",      # Blue
                AlertLevel.WARNING: "\033[93m",   # Yellow
                AlertLevel.ERROR: "\033[91m",     # Red
                AlertLevel.CRITICAL: "\033[95m"   # Magenta
            }
            reset_code = "\033[0m"
            
            color = color_codes.get(alert.level, "")
            print(f"{color}[{alert.level.upper()}] {alert.component}: {alert.message}{reset_code}")
        
        # File logging (if enabled)
        if self.config.get("alerts", {}).get("enable_file", True):
            self.logger.log(
                {"info": 20, "warning": 30, "error": 40, "critical": 50}.get(alert.level, 20),
                f"ALERT [{alert.level.upper()}] {alert.component}: {alert.message}"
            )
        
        # Email alerts (if enabled and configured)
        if self._should_send_email_alert(alert):
            self._send_email_alert(alert)
        
        # Custom handlers
        for handler in self.alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                self.logger.error(f"Error in custom alert handler: {e}")
    
    def _should_send_email_alert(self, alert: Alert) -> bool:
        """Determine if email should be sent for this alert."""
        email_config = self.config.get("alerts", {})
        
        if not email_config.get("enable_email", False):
            return False
        
        if not email_config.get("email_recipients"):
            return False
        
        # Only send email for warning, error, or critical alerts
        if alert.level in [AlertLevel.WARNING, AlertLevel.ERROR, AlertLevel.CRITICAL]:
            return True
        
        return False
    
    def _send_email_alert(self, alert: Alert):
        """Send alert via email."""
        if not EMAIL_AVAILABLE:
            self.logger.warning("Email functionality not available - skipping email alert")
            return
            
        try:
            email_config = self.config.get("alerts", {})
            smtp_config = email_config.get("smtp_settings", {})
            
            if not all([smtp_config.get("server"), smtp_config.get("username"), smtp_config.get("password")]):
                self.logger.warning("Email alert skipped - incomplete SMTP configuration")
                return
            
            # Create email message
            msg = MimeMultipart()
            msg['From'] = smtp_config["username"]
            msg['To'] = ", ".join(email_config["email_recipients"])
            msg['Subject'] = f"PowerTrader AI Alert: {alert.level.upper()} - {alert.component}"
            
            # Email body
            body = f"""
PowerTrader AI Alert

Level: {alert.level.upper()}
Component: {alert.component}
Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}

Message: {alert.message}

Details:
{json.dumps(alert.details, indent=2)}

Alert ID: {alert.alert_id}
"""
            msg.attach(MimeText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(smtp_config["server"], smtp_config.get("port", 587))
            server.starttls()
            server.login(smtp_config["username"], smtp_config["password"])
            text = msg.as_string()
            server.sendmail(smtp_config["username"], email_config["email_recipients"], text)
            server.quit()
            
            self.logger.info(f"Email alert sent for {alert.alert_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to send email alert: {e}")
    
    def _cleanup_old_data(self):
        """Clean up old alerts and metrics."""
        # Clean up old alerts
        retention_days = self.config.get("alerts_retention_days", 7)
        cutoff_time = datetime.now() - timedelta(days=retention_days)
        self.alerts = [a for a in self.alerts if a.timestamp > cutoff_time]
    
    def get_system_health(self) -> SystemHealth:
        """Get current system health status."""
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        # Check component health
        components = {
            "monitoring": self.is_running,
            "paper_trading": self.paper_account is not None,
            "risk_management": self.risk_manager is not None,
            "performance_monitor": True
        }
        
        # Count alerts by level
        recent_alerts = [a for a in self.alerts if a.timestamp > datetime.now() - timedelta(hours=1)]
        alert_counts = {
            "info": len([a for a in recent_alerts if a.level == AlertLevel.INFO]),
            "warning": len([a for a in recent_alerts if a.level == AlertLevel.WARNING]),
            "error": len([a for a in recent_alerts if a.level == AlertLevel.ERROR]),
            "critical": len([a for a in recent_alerts if a.level == AlertLevel.CRITICAL])
        }
        
        # Overall health status
        if alert_counts["critical"] > 0:
            status = "critical"
        elif alert_counts["error"] > 0:
            status = "error" 
        elif alert_counts["warning"] > 2:
            status = "warning"
        else:
            status = "healthy"
        
        # Latest metrics
        latest_metrics = {}
        for metric_name, metric_list in self.metrics.items():
            if metric_list:
                latest_metrics[metric_name] = metric_list[-1].value
        
        return SystemHealth(
            status=status,
            components=components,
            metrics=latest_metrics,
            alerts_count=alert_counts,
            uptime_seconds=uptime
        )
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data."""
        health = self.get_system_health()
        
        # Recent metrics for charts
        chart_data = {}
        for metric_name, metric_list in self.metrics.items():
            if len(metric_list) >= 2:  # Only include metrics with history
                chart_data[metric_name] = [
                    {
                        "timestamp": m.timestamp.isoformat(),
                        "value": m.value,
                        "unit": m.unit
                    }
                    for m in metric_list[-100:]  # Last 100 points
                ]
        
        return {
            "system_health": {
                "status": health.status,
                "uptime_seconds": health.uptime_seconds,
                "components": health.components,
                "alerts_count": health.alerts_count,
                "last_check": health.last_check.isoformat()
            },
            "current_metrics": health.metrics,
            "chart_data": chart_data,
            "recent_alerts": [
                {
                    "alert_id": a.alert_id,
                    "level": a.level,
                    "component": a.component,
                    "message": a.message,
                    "timestamp": a.timestamp.isoformat()
                }
                for a in sorted(self.alerts[-20:], key=lambda x: x.timestamp, reverse=True)
            ]
        }

# Example usage
async def demo_live_monitoring():
    """Demonstrate live monitoring functionality."""
    print("PowerTrader AI Live Monitoring Demo")
    print("=" * 40)
    
    # Create monitoring system
    monitor = LiveMonitor()
    
    # Create and register paper trading account
    from pt_paper_trading import PaperTradingAccount, OrderType, OrderSide
    from decimal import Decimal
    
    account = PaperTradingAccount(Decimal('10000'))
    monitor.register_paper_account(account)
    
    # Add custom alert handler
    def custom_alert_handler(alert: Alert):
        print(f"Custom Handler: {alert.level} alert from {alert.component}")
    
    monitor.add_alert_handler(custom_alert_handler)
    
    # Start monitoring
    monitor.start_monitoring()
    
    print("Monitoring started. Simulating some trading activity...")
    
    # Simulate trading activity
    account.place_order("BTC", OrderType.MARKET, OrderSide.BUY, Decimal('0.1'))
    await asyncio.sleep(2)
    
    account.place_order("ETH", OrderType.MARKET, OrderSide.BUY, Decimal('2.0'))
    await asyncio.sleep(2)
    
    # Update prices to simulate market movement
    account.update_market_prices()
    
    # Get dashboard data
    dashboard = monitor.get_dashboard_data()
    print("\nCurrent System Health:", dashboard["system_health"]["status"])
    print("Active Alerts:", len(dashboard["recent_alerts"]))
    
    # Show some key metrics
    if "current_metrics" in dashboard:
        for metric_name, value in list(dashboard["current_metrics"].items())[:5]:
            print(f"  {metric_name}: {value}")
    
    # Run for a bit to collect metrics
    await asyncio.sleep(5)
    
    # Stop monitoring
    monitor.stop_monitoring()
    print("\nMonitoring stopped.")

if __name__ == "__main__":
    # Run demo
    asyncio.run(demo_live_monitoring())