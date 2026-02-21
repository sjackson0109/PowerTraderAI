"""
PowerTrader AI Real-Time Monitoring Dashboard

Provides live monitoring of risk management and cost analysis systems.
"""

import time
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import colorama
from colorama import Fore, Style, Back
from pt_risk import RiskManager, RiskLevel
from pt_cost import CostManager, PerformanceTier, PerformanceMetrics

# Initialize colorama
colorama.init(autoreset=True)

class MonitoringDashboard:
    """
    Real-time monitoring dashboard for PowerTrader AI
    
    Displays live risk metrics, cost analysis, performance tracking,
    and system health monitoring.
    """
    
    def __init__(self, risk_manager: RiskManager, cost_manager: CostManager):
        self.risk_manager = risk_manager
        self.cost_manager = cost_manager
        self.start_time = datetime.now()
        self.refresh_interval = 5  # seconds
        
        # Historical tracking
        self.portfolio_history = []
        self.alert_history = []
        self.performance_snapshots = []
        
    def clear_screen(self):
        """Clear the terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def format_currency(self, amount: float) -> str:
        """Format currency with appropriate colors"""
        if amount >= 0:
            return f"{Fore.GREEN}${amount:,.2f}{Style.RESET_ALL}"
        else:
            return f"{Fore.RED}-${abs(amount):,.2f}{Style.RESET_ALL}"
    
    def format_percentage(self, pct: float) -> str:
        """Format percentage with appropriate colors"""
        if pct >= 0:
            return f"{Fore.GREEN}{pct:+.2f}%{Style.RESET_ALL}"
        else:
            return f"{Fore.RED}{pct:+.2f}%{Style.RESET_ALL}"
    
    def format_risk_level(self, level: RiskLevel) -> str:
        """Format risk level with colors"""
        colors = {
            RiskLevel.LOW: Fore.GREEN,
            RiskLevel.MEDIUM: Fore.YELLOW,
            RiskLevel.HIGH: Fore.RED,
            RiskLevel.CRITICAL: Fore.MAGENTA
        }
        return f"{colors.get(level, Fore.WHITE)}{level.value.upper()}{Style.RESET_ALL}"
    
    def display_header(self):
        """Display dashboard header"""
        runtime = datetime.now() - self.start_time
        print(f"{Back.BLUE}{Fore.WHITE} PowerTrader AI - Live Monitoring Dashboard {Style.RESET_ALL}")
        print(f"Runtime: {runtime} | Last Update: {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 80)
    
    def display_system_status(self):
        """Display overall system status"""
        print(f"{Back.WHITE}{Fore.BLACK} SYSTEM STATUS {Style.RESET_ALL}")
        
        # Trading status
        trading_status = "ACTIVE" if not self.risk_manager.is_trading_halted() else "HALTED"
        status_color = Fore.GREEN if trading_status == "ACTIVE" else Fore.RED
        print(f"Trading Status: {status_color}{trading_status}{Style.RESET_ALL}")
        
        # Emergency stop status
        emergency_status = "ACTIVE" if self.risk_manager.emergency_stop_active else "INACTIVE"
        emergency_color = Fore.RED if emergency_status == "ACTIVE" else Fore.GREEN
        print(f"Emergency Stop: {emergency_color}{emergency_status}{Style.RESET_ALL}")
        
        # Risk level
        print(f"Risk Level: {self.format_risk_level(self.risk_manager.current_risk_level)}")
        
        # Cost tier
        print(f"Cost Tier: {Fore.CYAN}{self.cost_manager.tier.value.title()}{Style.RESET_ALL}")
        print()
    
    def display_portfolio_summary(self, portfolio_value: float):
        """Display portfolio summary"""
        print(f"{Back.WHITE}{Fore.BLACK} PORTFOLIO SUMMARY {Style.RESET_ALL}")
        
        # Current portfolio value
        print(f"Current Value: {self.format_currency(portfolio_value)}")
        
        # Initial value comparison
        if hasattr(self.risk_manager, 'initial_portfolio_value') and self.risk_manager.initial_portfolio_value:
            initial_value = self.risk_manager.initial_portfolio_value
            change = portfolio_value - initial_value
            change_pct = (change / initial_value) * 100 if initial_value > 0 else 0
            print(f"Total Return: {self.format_currency(change)} ({self.format_percentage(change_pct)})")
        
        # Daily high/low
        today_history = [p for p in self.portfolio_history if 
                        p['timestamp'] > datetime.now() - timedelta(days=1)]
        if today_history:
            today_high = max(p['value'] for p in today_history)
            today_low = min(p['value'] for p in today_history)
            print(f"Today's High: {self.format_currency(today_high)}")
            print(f"Today's Low: {self.format_currency(today_low)}")
        
        print()
    
    def display_risk_metrics(self):
        """Display risk management metrics"""
        print(f"{Back.WHITE}{Fore.BLACK} RISK MANAGEMENT {Style.RESET_ALL}")
        
        # Portfolio limits
        limits = self.risk_manager.portfolio_limits
        print(f"Max Position Size: {limits['max_position_size_pct']:.1f}%")
        print(f"Max Daily Loss: {limits['max_daily_loss_pct']:.1f}%")
        print(f"Max Drawdown: {limits['max_drawdown_pct']:.1f}%")
        
        # Current positions
        if self.risk_manager.position_tracker:
            print(f"\n{Fore.CYAN}Active Positions:{Style.RESET_ALL}")
            for symbol, position in self.risk_manager.position_tracker.items():
                value = position['quantity'] * position['avg_price']
                print(f"  {symbol}: {position['quantity']:.4f} @ {self.format_currency(position['avg_price'])} = {self.format_currency(value)}")
        
        # Recent alerts
        recent_alerts = [a for a in self.alert_history if 
                        a['timestamp'] > datetime.now() - timedelta(hours=1)]
        if recent_alerts:
            print(f"\n{Fore.YELLOW}Recent Alerts (1h):{Style.RESET_ALL}")
            for alert in recent_alerts[-3:]:  # Show last 3
                time_str = alert['timestamp'].strftime('%H:%M:%S')
                print(f"  {time_str}: {alert['message']}")
        
        print()
    
    def display_cost_analysis(self):
        """Display cost analysis"""
        print(f"{Back.WHITE}{Fore.BLACK} COST ANALYSIS {Style.RESET_ALL}")
        
        # Monthly costs breakdown
        monthly_costs = self.cost_manager.calculate_monthly_costs()
        print(f"Monthly Costs: {self.format_currency(monthly_costs.total_monthly)}")
        print(f"Annual Projection: {self.format_currency(monthly_costs.total_annual)}")
        
        # Cost breakdown
        print(f"\n{Fore.CYAN}Cost Breakdown:{Style.RESET_ALL}")
        categories = [
            ("Infrastructure", monthly_costs.infrastructure),
            ("Data Feeds", monthly_costs.data_feeds),
            ("Personnel", monthly_costs.personnel),
            ("Software", monthly_costs.software),
            ("Compliance", monthly_costs.compliance),
            ("Legal", monthly_costs.legal),
            ("Insurance", monthly_costs.insurance)
        ]
        
        for name, amount in sorted(categories, key=lambda x: x[1], reverse=True):
            if amount > 0:
                print(f"  {name}: {self.format_currency(amount)}")
        
        print()
    
    def display_performance_metrics(self, portfolio_value: float):
        """Display performance metrics"""
        print(f"{Back.WHITE}{Fore.BLACK} PERFORMANCE METRICS {Style.RESET_ALL}")
        
        if len(self.portfolio_history) < 2:
            print("Insufficient data for performance analysis")
            print()
            return
        
        # Calculate basic metrics
        values = [p['value'] for p in self.portfolio_history]
        returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]
        
        # Performance statistics
        if returns:
            avg_return = sum(returns) / len(returns)
            max_return = max(returns)
            min_return = min(returns)
            
            print(f"Avg Return: {self.format_percentage(avg_return * 100)}")
            print(f"Best Period: {self.format_percentage(max_return * 100)}")
            print(f"Worst Period: {self.format_percentage(min_return * 100)}")
        
        # Drawdown analysis
        peak_value = max(values)
        current_drawdown = (portfolio_value - peak_value) / peak_value * 100 if peak_value > 0 else 0
        print(f"Current Drawdown: {self.format_percentage(current_drawdown)}")
        
        print()
    
    def display_alerts_and_warnings(self):
        """Display active alerts and warnings"""
        print(f"{Back.WHITE}{Fore.BLACK} ALERTS & WARNINGS {Style.RESET_ALL}")
        
        # Check for active warnings
        warnings = []
        
        # Risk-based warnings
        if self.risk_manager.current_risk_level == RiskLevel.HIGH:
            warnings.append("HIGH RISK: Portfolio in high risk zone")
        elif self.risk_manager.current_risk_level == RiskLevel.CRITICAL:
            warnings.append("CRITICAL RISK: Portfolio in critical risk zone")
        
        # Cost-based warnings
        monthly_costs = self.cost_manager.calculate_monthly_costs()
        if hasattr(self.risk_manager, 'initial_portfolio_value') and self.risk_manager.initial_portfolio_value:
            monthly_burn_rate = monthly_costs.total_monthly / self.risk_manager.initial_portfolio_value
            if monthly_burn_rate > 0.05:  # More than 5% monthly burn
                warnings.append(f"HIGH BURN RATE: {monthly_burn_rate:.1%} monthly cost burn rate")
        
        if warnings:
            for warning in warnings:
                print(f"{Fore.YELLOW}⚠ {warning}{Style.RESET_ALL}")
        else:
            print(f"{Fore.GREEN}✅ No active warnings{Style.RESET_ALL}")
        
        print()
    
    def display_trading_statistics(self):
        """Display trading statistics"""
        print(f"{Back.WHITE}{Fore.BLACK} TRADING STATISTICS {Style.RESET_ALL}")
        
        # This would be populated from actual trading data
        print("Daily Trade Count: 0")
        print("Weekly Trade Count: 0") 
        print("Success Rate: N/A")
        print("Avg Trade Size: N/A")
        print()
    
    def update_data(self, portfolio_value: float):
        """Update monitoring data"""
        # Update portfolio history
        self.portfolio_history.append({
            'timestamp': datetime.now(),
            'value': portfolio_value
        })
        
        # Keep only last 24 hours of data
        cutoff_time = datetime.now() - timedelta(hours=24)
        self.portfolio_history = [p for p in self.portfolio_history if p['timestamp'] > cutoff_time]
        
        # Update risk manager
        self.risk_manager.update_portfolio_value(portfolio_value)
        
        # Check for new alerts
        risk_status = self.risk_manager.check_emergency_conditions(portfolio_value)
        if risk_status['warnings']:
            for warning in risk_status['warnings']:
                self.alert_history.append({
                    'timestamp': datetime.now(),
                    'type': 'warning',
                    'message': warning
                })
    
    def run_dashboard(self):
        """Run the live monitoring dashboard"""
        print(f"{Fore.CYAN}Starting PowerTrader AI Monitoring Dashboard...{Style.RESET_ALL}")
        print("Press Ctrl+C to stop")
        time.sleep(2)
        
        try:
            while True:
                # Mock portfolio value for demonstration
                # In real implementation, this would come from the trading system
                base_value = 100000
                variance = 5000
                portfolio_value = base_value + (time.time() % 100 - 50) * 100
                
                # Update data
                self.update_data(portfolio_value)
                
                # Clear and redraw
                self.clear_screen()
                
                # Display dashboard sections
                self.display_header()
                self.display_system_status()
                self.display_portfolio_summary(portfolio_value)
                self.display_risk_metrics()
                self.display_cost_analysis()
                self.display_performance_metrics(portfolio_value)
                self.display_alerts_and_warnings()
                self.display_trading_statistics()
                
                print(f"{Fore.CYAN}Refreshing every {self.refresh_interval} seconds...{Style.RESET_ALL}")
                time.sleep(self.refresh_interval)
                
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Dashboard stopped by user{Style.RESET_ALL}")

def main():
    """Main entry point"""
    print(f"{Fore.CYAN}Initializing monitoring systems...{Style.RESET_ALL}")
    
    # Initialize systems
    risk_manager = RiskManager()
    cost_manager = CostManager(PerformanceTier.PROFESSIONAL)
    
    # Set initial portfolio value
    risk_manager.initial_portfolio_value = 100000
    
    # Create and run dashboard
    dashboard = MonitoringDashboard(risk_manager, cost_manager)
    dashboard.run_dashboard()

if __name__ == "__main__":
    main()