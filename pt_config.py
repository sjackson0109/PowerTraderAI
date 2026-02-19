"""
PowerTrader AI Configuration System

Centralized configuration for risk management and cost control systems.
"""

import json
import os
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
from enum import Enum

class ConfigTier(Enum):
    """Configuration tiers for different operational scales"""
    PERSONAL = "personal"
    PROFESSIONAL = "professional" 
    ENTERPRISE = "enterprise"

@dataclass
class RiskConfiguration:
    """Risk management configuration"""
    # Portfolio limits
    max_position_size_pct: float = 10.0
    max_daily_loss_pct: float = 5.0
    max_drawdown_pct: float = 20.0
    max_correlation_exposure: float = 25.0
    
    # Trading limits
    max_trades_per_hour: int = 20
    max_order_size_usd: float = 10000
    min_order_size_usd: float = 10
    
    # Emergency thresholds
    emergency_drawdown_pct: float = 25.0
    emergency_daily_loss_pct: float = 10.0
    circuit_breaker_enabled: bool = True
    
    # Volatility controls
    volatility_window_hours: int = 24
    max_volatility_threshold: float = 0.5
    volatility_scaling_enabled: bool = True

@dataclass  
class CostConfiguration:
    """Cost management configuration"""
    # Tier settings
    performance_tier: str = "professional"
    
    # Infrastructure costs (monthly USD)
    infrastructure_budget: float = 1000.0
    data_feed_budget: float = 500.0
    personnel_budget: float = 5000.0
    
    # Trading cost limits
    max_trading_fees_pct: float = 0.5
    target_cost_per_trade: float = 2.0
    
    # Performance targets
    target_monthly_return_pct: float = 3.0
    minimum_sharpe_ratio: float = 1.0
    maximum_cost_ratio_pct: float = 15.0

@dataclass
class TradingConfiguration:
    """Trading system configuration"""
    # Basic settings
    trading_enabled: bool = True
    max_concurrent_trades: int = 10
    default_trade_size_pct: float = 2.0
    
    # DCA settings
    dca_enabled: bool = True
    dca_levels: list = None
    max_dca_levels: int = 5
    
    # Profit taking
    profit_target_pct: float = 5.0
    trailing_stop_enabled: bool = True
    trailing_gap_pct: float = 2.0
    
    # Risk integration
    respect_risk_limits: bool = True
    halt_on_emergency: bool = True

@dataclass
class MonitoringConfiguration:
    """Monitoring and alerting configuration"""
    # Dashboard settings
    dashboard_enabled: bool = True
    refresh_interval_seconds: int = 5
    
    # Alerting
    email_alerts_enabled: bool = False
    sms_alerts_enabled: bool = False
    console_alerts_enabled: bool = True
    
    # Logging
    log_level: str = "INFO"
    log_file_enabled: bool = True
    performance_logging_enabled: bool = True
    
    # Reporting
    daily_reports_enabled: bool = True
    weekly_reports_enabled: bool = True
    monthly_reports_enabled: bool = True

@dataclass
class PowerTraderConfig:
    """Master configuration for PowerTrader AI"""
    risk: RiskConfiguration = None
    cost: CostConfiguration = None
    trading: TradingConfiguration = None
    monitoring: MonitoringConfiguration = None
    
    # Meta configuration
    config_version: str = "1.0"
    tier: ConfigTier = ConfigTier.PROFESSIONAL
    environment: str = "production"
    
    def __post_init__(self):
        if self.risk is None:
            self.risk = RiskConfiguration()
        if self.cost is None:
            self.cost = CostConfiguration()
        if self.trading is None:
            self.trading = TradingConfiguration()
            self.trading.dca_levels = [-5, -10, -15, -25, -35]
        if self.monitoring is None:
            self.monitoring = MonitoringConfiguration()

class ConfigManager:
    """Configuration management system"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
    
    def _get_default_config_path(self) -> str:
        """Get default configuration file path"""
        base_dir = os.path.dirname(__file__)
        return os.path.join(base_dir, "powertrader_config.json")
    
    def _load_config(self) -> PowerTraderConfig:
        """Load configuration from file"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                return self._dict_to_config(data)
            except Exception as e:
                print(f"Error loading config: {e}")
                print("Using default configuration")
        
        return self._create_default_config()
    
    def _create_default_config(self) -> PowerTraderConfig:
        """Create default configuration based on tier"""
        return PowerTraderConfig()
    
    def _dict_to_config(self, data: Dict[str, Any]) -> PowerTraderConfig:
        """Convert dictionary to configuration object"""
        config = PowerTraderConfig()
        
        if 'risk' in data:
            config.risk = RiskConfiguration(**data['risk'])
        if 'cost' in data:
            config.cost = CostConfiguration(**data['cost'])
        if 'trading' in data:
            config.trading = TradingConfiguration(**data['trading'])
        if 'monitoring' in data:
            config.monitoring = MonitoringConfiguration(**data['monitoring'])
            
        # Set meta fields
        config.config_version = data.get('config_version', '1.0')
        config.tier = ConfigTier(data.get('tier', 'professional'))
        config.environment = data.get('environment', 'production')
        
        return config
    
    def save_config(self):
        """Save configuration to file"""
        try:
            data = asdict(self.config)
            data['tier'] = self.config.tier.value
            
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"Configuration saved to {self.config_path}")
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def update_tier(self, tier: ConfigTier):
        """Update configuration tier and adjust settings"""
        self.config.tier = tier
        self._adjust_for_tier(tier)
        
    def _adjust_for_tier(self, tier: ConfigTier):
        """Adjust configuration settings based on tier"""
        if tier == ConfigTier.PERSONAL:
            # Conservative settings for personal use
            self.config.risk.max_position_size_pct = 5.0
            self.config.risk.max_daily_loss_pct = 2.0
            self.config.risk.max_order_size_usd = 1000.0
            self.config.cost.infrastructure_budget = 100.0
            self.config.cost.personnel_budget = 0.0
            self.config.trading.max_concurrent_trades = 3
            
        elif tier == ConfigTier.PROFESSIONAL:
            # Balanced settings for professional use
            self.config.risk.max_position_size_pct = 10.0
            self.config.risk.max_daily_loss_pct = 5.0
            self.config.risk.max_order_size_usd = 10000.0
            self.config.cost.infrastructure_budget = 1000.0
            self.config.cost.personnel_budget = 5000.0
            self.config.trading.max_concurrent_trades = 10
            
        elif tier == ConfigTier.ENTERPRISE:
            # Aggressive settings for enterprise use
            self.config.risk.max_position_size_pct = 15.0
            self.config.risk.max_daily_loss_pct = 7.0
            self.config.risk.max_order_size_usd = 100000.0
            self.config.cost.infrastructure_budget = 10000.0
            self.config.cost.personnel_budget = 50000.0
            self.config.trading.max_concurrent_trades = 50
    
    def validate_config(self) -> Dict[str, Any]:
        """Validate configuration settings"""
        issues = []
        
        # Validate risk settings
        if self.config.risk.max_position_size_pct > 50:
            issues.append("Risk: Position size limit too high (>50%)")
        
        if self.config.risk.max_daily_loss_pct > 20:
            issues.append("Risk: Daily loss limit too high (>20%)")
            
        # Validate cost settings
        if self.config.cost.maximum_cost_ratio_pct > 30:
            issues.append("Cost: Cost ratio too high (>30%)")
            
        # Validate trading settings
        if self.config.trading.max_concurrent_trades > 100:
            issues.append("Trading: Too many concurrent trades (>100)")
            
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': []
        }
    
    def get_risk_config(self) -> RiskConfiguration:
        """Get risk management configuration"""
        return self.config.risk
    
    def get_cost_config(self) -> CostConfiguration:
        """Get cost management configuration"""
        return self.config.cost
    
    def get_trading_config(self) -> TradingConfiguration:
        """Get trading configuration"""
        return self.config.trading
    
    def get_monitoring_config(self) -> MonitoringConfiguration:
        """Get monitoring configuration"""
        return self.config.monitoring

def create_sample_configs():
    """Create sample configuration files for different tiers"""
    
    for tier in ConfigTier:
        config_manager = ConfigManager(f"config_{tier.value}.json")
        config_manager.update_tier(tier)
        config_manager.save_config()
        print(f"Created sample config for {tier.value} tier")

def main():
    """Main configuration utility"""
    import argparse
    
    parser = argparse.ArgumentParser(description="PowerTrader AI Configuration Manager")
    parser.add_argument('--create-samples', action='store_true', 
                       help='Create sample configuration files')
    parser.add_argument('--validate', type=str, 
                       help='Validate configuration file')
    parser.add_argument('--tier', type=str, choices=['personal', 'professional', 'enterprise'],
                       help='Set configuration tier')
    parser.add_argument('--config', type=str, default='powertrader_config.json',
                       help='Configuration file path')
    
    args = parser.parse_args()
    
    if args.create_samples:
        create_sample_configs()
        return
    
    config_manager = ConfigManager(args.config)
    
    if args.validate:
        validation = config_manager.validate_config()
        if validation['valid']:
            print("✅ Configuration is valid")
        else:
            print("❌ Configuration has issues:")
            for issue in validation['issues']:
                print(f"  - {issue}")
    
    if args.tier:
        tier = ConfigTier(args.tier)
        config_manager.update_tier(tier)
        config_manager.save_config()
        print(f"Configuration updated to {tier.value} tier")

if __name__ == "__main__":
    main()