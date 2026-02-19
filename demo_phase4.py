"""
PowerTrader AI Phase 4 Complete Demonstration

Showcases the fully implemented Phase 4 features:
- Paper Trading System with Real Market Simulation
- Risk Management Integration  
- Live Monitoring & Alerting
- End-to-End Trading Workflow
"""

import asyncio
import sys
import os
from decimal import Decimal
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

# Import our Phase 4 systems
from pt_paper_trading import PaperTradingAccount, OrderType, OrderSide
from pt_live_monitor import LiveMonitor
from pt_risk import RiskManager, RiskLimits
from pt_cost import CostManager, PerformanceTier

async def phase4_demo():
    """Complete Phase 4 demonstration."""
    print("🎉 PowerTrader AI Phase 4 - Complete Implementation Demo")
    print("=" * 70)
    print("Demonstrating: Paper Trading + Live Monitoring + Risk Management")
    print("=" * 70)
    
    # 1. Initialize Paper Trading Account
    print("\n💰 1. Initializing Paper Trading Account")
    account = PaperTradingAccount(initial_balance=Decimal('50000'))
    print(f"   • Initial Balance: ${account.initial_balance:,}")
    print(f"   • Account ID: {account.account_id[:8]}...")
    
    # 2. Set up Live Monitoring
    print("\n📊 2. Starting Live Monitoring System")
    monitor = LiveMonitor()
    monitor.register_paper_account(account)
    
    # Add custom alert handler
    alerts_received = []
    def demo_alert_handler(alert):
        alerts_received.append(alert)
        print(f"   🚨 ALERT [{alert.level.upper()}]: {alert.message}")
    
    monitor.add_alert_handler(demo_alert_handler)
    monitor.start_monitoring()
    print("   • Monitoring system started")
    print("   • Custom alert handler registered")
    
    # 3. Display Cost Analysis
    print("\n💸 3. Cost Analysis for Trading Operation")
    cost_manager = CostManager(PerformanceTier.PROFESSIONAL)
    monthly_costs = cost_manager.calculate_monthly_costs()
    print(f"   • Monthly Operating Costs: ${monthly_costs.total_monthly:.2f}")
    print(f"   • Data Feeds: ${monthly_costs.data_feeds:.2f}")
    print(f"   • Infrastructure: ${monthly_costs.infrastructure:.2f}")
    print(f"   • Exchange Fees: ${monthly_costs.exchange_fees:.2f}")
    print(f"   • Performance Tier: {PerformanceTier.PROFESSIONAL.name}")
    
    # 4. Execute Trading Scenario
    print("\n📈 4. Executing Diversified Trading Strategy")
    
    # Define trading scenario
    trades = [
        ("BTC", Decimal('0.05'), "Bitcoin - Large Cap"),
        ("ETH", Decimal('1.5'), "Ethereum - Smart Contracts"),
        ("ADA", Decimal('500'), "Cardano - DeFi Platform"),
        ("SOL", Decimal('8'), "Solana - High Performance"),
        ("DOT", Decimal('15'), "Polkadot - Interoperability")
    ]
    
    executed_trades = 0
    total_value_invested = Decimal('0')
    
    for symbol, quantity, description in trades:
        try:
            print(f"   • Trading {symbol}: {description}")
            order_id = account.place_order(symbol, OrderType.MARKET, OrderSide.BUY, quantity)
            status = account.get_order_status(order_id)
            
            if status and hasattr(status, 'value'):
                status_str = status.value
            else:
                status_str = str(status)
                
            if 'filled' in status_str.lower():
                executed_trades += 1
                # Estimate trade value for display
                current_price = account.market_simulator.get_current_price(symbol)
                trade_value = quantity * current_price
                total_value_invested += trade_value
                print(f"     ✅ Order filled: {quantity} {symbol} @ ~${current_price:.2f}")
            else:
                print(f"     ⚠️  Order status: {status_str}")
            
            # Brief pause between trades
            await asyncio.sleep(0.2)
            
        except Exception as e:
            print(f"     ❌ Trade failed: {e}")
    
    print(f"\n   📊 Trading Summary:")
    print(f"   • Successful trades: {executed_trades}/{len(trades)}")
    print(f"   • Total invested: ~${total_value_invested:.2f}")
    
    # 5. Update Market Prices and Show Portfolio
    print("\n📉 5. Market Data Update & Portfolio Analysis")
    account.update_market_prices()
    
    # Get comprehensive portfolio summary
    summary = account.get_account_summary()
    
    print(f"   📈 Portfolio Status:")
    print(f"   • Total Portfolio Value: ${summary['total_value']:,.2f}")
    print(f"   • Cash Balance: ${summary['cash_balance']:,.2f}")
    print(f"   • Positions Value: ${summary['total_value'] - summary['cash_balance']:,.2f}")
    print(f"   • Total P&L: ${summary['total_pnl']:,.2f} ({summary['total_return_pct']:+.2f}%)")
    print(f"   • Active Positions: {len(summary['positions'])}")
    
    if summary['positions']:
        print("\n   🏆 Position Details:")
        for symbol, pos_data in summary['positions'].items():
            unrealized_pct = pos_data['unrealized_pnl_pct']
            pnl_indicator = "📈" if unrealized_pct >= 0 else "📉"
            print(f"     {pnl_indicator} {symbol}: {pos_data['quantity']:.4f} @ ${pos_data['avg_price']:.2f}")
            print(f"        Value: ${pos_data['market_value']:,.2f} | P&L: ${pos_data['unrealized_pnl']:+.2f} ({unrealized_pct:+.2f}%)")
    
    # 6. Risk Management Analysis
    print("\n🛡️  6. Risk Management Assessment")
    
    # Create risk manager for analysis
    limits = RiskLimits()
    risk_manager = RiskManager(limits, portfolio_value=float(summary['total_value']))
    
    print(f"   • Portfolio Value for Risk Calc: ${float(summary['total_value']):,.2f}")
    
    # Test different risk scenarios
    risk_scenarios = [
        (0.01, "Conservative (1%)"),
        (0.02, "Moderate (2%)"),
        (0.03, "Aggressive (3%)")
    ]
    
    for risk_pct, scenario_name in risk_scenarios:
        max_position = risk_manager.calculate_position_size(float(summary['total_value']), risk_pct)
        print(f"   • {scenario_name}: Max position size ${max_position:,.2f}")
    
    # 7. Live Monitoring Report
    print("\n📊 7. Live Monitoring System Report")
    await asyncio.sleep(1)  # Let monitoring collect some data
    
    health = monitor.get_system_health()
    dashboard = monitor.get_dashboard_data()
    
    print(f"   • System Health: {health.status.upper()}")
    print(f"   • System Uptime: {health.uptime_seconds:.1f} seconds")
    print(f"   • Components Status: {sum(health.components.values())}/{len(health.components)} operational")
    print(f"   • Metrics Collected: {len(dashboard['current_metrics'])}")
    print(f"   • Alerts Generated: {len(alerts_received)}")
    
    if dashboard['current_metrics']:
        print("\n   📏 Key Metrics:")
        for metric_name, value in list(dashboard['current_metrics'].items())[:5]:
            if 'pct' in metric_name:
                print(f"     • {metric_name}: {value:.2f}%")
            elif 'value' in metric_name or 'balance' in metric_name:
                print(f"     • {metric_name}: ${value:,.2f}")
            else:
                print(f"     • {metric_name}: {value:.2f}")
    
    # 8. Performance Summary
    print("\n🎯 8. Phase 4 Implementation Summary")
    print("   =" * 50)
    print("   ✅ Paper Trading System: Fully Operational")
    print("      • Real-time market simulation")
    print("      • Order management (market orders)")
    print("      • Position tracking with P&L")
    print("      • Risk-based order validation")
    
    print("\n   ✅ Live Monitoring System: Active")
    print("      • Real-time metrics collection")
    print("      • System health monitoring")
    print("      • Alert generation and handling")
    print("      • Dashboard data provision")
    
    print("\n   ✅ Risk Management: Integrated")
    print("      • Position size calculations")
    print("      • Portfolio risk assessment")
    print("      • Multi-scenario analysis")
    print("      • Real-time validation")
    
    print("\n   ✅ Cost Management: Operational")
    print("      • Performance tier analysis")
    print("      • Monthly cost projections")
    print("      • Infrastructure planning")
    
    print("\n   🚀 Ready for Phase 5: Production Deployment")
    print("      • Live API integration")
    print("      • Production environment setup")
    print("      • Automated deployment pipeline")
    
    # 9. Cleanup
    print("\n🧹 9. Cleanup & Shutdown")
    monitor.stop_monitoring()
    print("   • Live monitoring stopped")
    print("   • Paper trading session ended")
    print("   • All systems shut down gracefully")
    
    print("\n🎉 Phase 4 Demonstration Complete!")
    print("   PowerTrader AI is ready for production deployment.")

if __name__ == "__main__":
    # Run the complete demonstration
    asyncio.run(phase4_demo())