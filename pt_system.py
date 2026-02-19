"""
PowerTrader AI Integration Module
Orchestrates all components and provides unified API for the trading system.
"""

import asyncio
import threading
import signal
import sys
import atexit
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
import logging
from pathlib import Path

# Import all PowerTrader components
from pt_config import ConfigurationManager, TradingConfig, ExchangeConfig
from pt_logging import PowerTraderLogger, configure_logging, shutdown_logging
from pt_performance import PerformanceMonitor, performance_monitor, cleanup_performance_monitoring
from pt_errors import ErrorHandler, error_handler, PowerTraderError
from pt_utils import SafeFileHandler, PerformanceTimer
from pt_testing import TradingStrategyTester, ComponentTester, run_comprehensive_tests

@dataclass
class SystemStatus:
    """Current system status and health information."""
    status: str  # running, stopped, error, starting, stopping
    uptime_seconds: float = 0.0
    last_error: Optional[str] = None
    components: Dict[str, bool] = field(default_factory=dict)
    performance_summary: Dict[str, Any] = field(default_factory=dict)
    configuration_summary: Dict[str, Any] = field(default_factory=dict)
    error_summary: Dict[str, Any] = field(default_factory=dict)

class PowerTraderSystem:
    """
    Main system orchestrator for PowerTrader AI.
    Manages all components, configuration, monitoring, and lifecycle.
    """
    
    def __init__(self, config_dir: str = "config", data_dir: str = "data"):
        """
        Initialize PowerTrader AI system.
        
        Args:
            config_dir: Configuration directory path
            data_dir: Data directory path
        """
        self.config_dir = Path(config_dir)
        self.data_dir = Path(data_dir)
        self.start_time = None
        self.is_running = False
        self.shutdown_handlers: List[Callable] = []
        
        # Component instances
        self.config_manager: Optional[ConfigurationManager] = None
        self.logger: Optional[PowerTraderLogger] = None
        self.performance_monitor: Optional[PerformanceMonitor] = None
        self.error_handler: Optional[ErrorHandler] = None
        
        # System monitoring
        self.status = SystemStatus(status="stopped")
        self.health_check_interval = 60.0  # seconds
        self.health_check_thread: Optional[threading.Thread] = None
        
        # Ensure directories exist
        self._create_directories()
        
        # Register cleanup handlers
        atexit.register(self.shutdown)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _create_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        directories = [
            self.config_dir,
            self.data_dir,
            self.data_dir / "logs",
            self.data_dir / "backups",
            self.data_dir / "cache"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def _signal_handler(self, signum, frame) -> None:
        """Handle system signals for graceful shutdown."""
        print(f"\\nReceived signal {signum}, shutting down gracefully...")
        self.shutdown()
        sys.exit(0)
    
    def initialize(self) -> bool:
        """
        Initialize all system components.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            self.status.status = "starting"
            print("Initializing PowerTrader AI...")
            
            # Initialize configuration management
            self._initialize_configuration()
            
            # Initialize logging
            self._initialize_logging()
            
            # Initialize performance monitoring
            self._initialize_performance_monitoring()
            
            # Initialize error handling
            self._initialize_error_handling()
            
            # Run component tests
            self._run_startup_tests()
            
            # Update system status
            self.status.status = "running"
            self.status.components = {
                "configuration": self.config_manager is not None,
                "logging": self.logger is not None,
                "performance": self.performance_monitor is not None,
                "error_handling": self.error_handler is not None
            }
            
            print("PowerTrader AI initialized successfully!")
            return True
            
        except Exception as e:
            self.status.status = "error"
            self.status.last_error = str(e)
            print(f"Failed to initialize PowerTrader AI: {e}")
            return False
    
    def _initialize_configuration(self) -> None:
        """Initialize configuration management."""
        print("  Initializing configuration management...")
        
        self.config_manager = ConfigurationManager(
            config_dir=self.config_dir,
            enable_hot_reload=True
        )
        
        # Add change callback to update logging when config changes
        self.config_manager.add_change_callback(self._on_configuration_changed)
        
        print(f"    Configuration loaded from: {self.config_dir}")
        print(f"    Environment: {self.config_manager.environment}")
    
    def _initialize_logging(self) -> None:
        """Initialize logging system."""
        print("  Initializing logging system...")
        
        # Get system configuration
        system_config = self.config_manager.system if self.config_manager else None
        
        log_file = None
        if system_config:
            log_file = self.data_dir / "logs" / Path(system_config.log_file_path).name
        else:
            log_file = self.data_dir / "logs" / "powertrader.log"
        
        # Configure logging
        configure_logging(
            log_level="INFO",
            log_file=str(log_file),
            json_output=True,
            colored_console=True,
            enable_performance_logging=True,
            enable_audit_logging=True,
            enable_trade_logging=True
        )
        
        self.logger = PowerTraderLogger("PowerTrader")
        self.logger.configure(
            log_level="INFO",
            log_file=str(log_file),
            json_output=True
        )
        
        print(f"    Logging configured: {log_file}")
        
        # Log system startup
        self.logger.log_audit("system_startup", details={
            "config_dir": str(self.config_dir),
            "data_dir": str(self.data_dir),
            "startup_time": datetime.now().isoformat()
        })
    
    def _initialize_performance_monitoring(self) -> None:
        """Initialize performance monitoring."""
        print("  Initializing performance monitoring...")
        
        # Use global performance monitor
        self.performance_monitor = performance_monitor
        
        # Start monitoring
        self.performance_monitor.start_system_monitoring()
        
        print("    Performance monitoring started")
    
    def _initialize_error_handling(self) -> None:
        """Initialize error handling."""
        print("  Initializing error handling...")
        
        # Use global error handler
        self.error_handler = error_handler
        
        print("    Error handling configured")
    
    def _run_startup_tests(self) -> None:
        """Run startup component tests."""
        print("  Running startup tests...")
        
        try:
            test_results = run_comprehensive_tests()
            
            passed = test_results['component_tests']['passed']
            total = test_results['component_tests']['total']
            
            print(f"    Component tests: {passed}/{total} passed")
            
            if passed < total:
                print("    Warning: Some component tests failed!")
                for result in test_results['results']:
                    if not result['passed']:
                        print(f"      - {result['name']}: {result['error']}")
            
        except Exception as e:
            print(f"    Warning: Startup tests failed: {e}")
    
    def _on_configuration_changed(self) -> None:
        """Handle configuration changes."""
        if self.logger:
            self.logger.get_logger().info("Configuration changed, updating system...")
        
        # Update logging configuration if needed
        try:
            self._update_logging_configuration()
        except Exception as e:
            if self.logger:
                self.logger.log_error_with_context(
                    "Failed to update logging configuration", 
                    error=e
                )
    
    def _update_logging_configuration(self) -> None:
        """Update logging configuration based on current settings."""
        if not self.config_manager or not self.logger:
            return
        
        system_config = self.config_manager.system
        
        # Update log level if it changed
        current_level = self.logger.get_logger().level
        new_level = getattr(logging, system_config.log_level.upper())
        
        if current_level != new_level:
            self.logger.get_logger().setLevel(new_level)
            self.logger.get_logger().info(f"Log level changed to {system_config.log_level}")
    
    def start(self) -> bool:
        """
        Start the PowerTrader AI system.
        
        Returns:
            True if started successfully, False otherwise
        """
        if self.is_running:
            print("PowerTrader AI is already running")
            return True
        
        if not self.initialize():
            return False
        
        try:
            self.start_time = datetime.now()
            self.is_running = True
            
            # Start health monitoring
            self._start_health_monitoring()
            
            if self.logger:
                self.logger.get_logger().info("PowerTrader AI system started successfully")
                self.logger.log_audit("system_started")
            
            return True
            
        except Exception as e:
            self.status.status = "error"
            self.status.last_error = str(e)
            print(f"Failed to start PowerTrader AI: {e}")
            return False
    
    def _start_health_monitoring(self) -> None:
        """Start background health monitoring."""
        def health_monitor():
            while self.is_running:
                try:
                    self._update_system_status()
                    threading.Event().wait(self.health_check_interval)
                except Exception as e:
                    if self.logger:
                        self.logger.log_error_with_context(
                            "Health monitoring error", 
                            error=e
                        )
        
        self.health_check_thread = threading.Thread(
            target=health_monitor,
            daemon=True,
            name="HealthMonitor"
        )
        self.health_check_thread.start()
    
    def _update_system_status(self) -> None:
        """Update system status information."""
        if not self.is_running:
            return
        
        try:
            # Calculate uptime
            if self.start_time:
                self.status.uptime_seconds = (datetime.now() - self.start_time).total_seconds()
            
            # Get performance summary
            if self.performance_monitor:
                self.status.performance_summary = self.performance_monitor.get_system_summary()
            
            # Get configuration summary
            if self.config_manager:
                self.status.configuration_summary = {
                    'environment': self.config_manager.environment,
                    'config_files': len(self.config_manager.watched_files),
                    'hot_reload': self.config_manager.enable_hot_reload
                }
            
            # Get error summary
            if self.error_handler:
                self.status.error_summary = self.error_handler.get_error_summary()
            
        except Exception as e:
            if self.logger:
                self.logger.log_error_with_context(
                    "Failed to update system status", 
                    error=e
                )
    
    def get_system_status(self) -> SystemStatus:
        """Get current system status."""
        self._update_system_status()
        return self.status
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get comprehensive system information."""
        status = self.get_system_status()
        
        info = {
            'system': {
                'status': status.status,
                'uptime_seconds': status.uptime_seconds,
                'start_time': self.start_time.isoformat() if self.start_time else None,
                'last_error': status.last_error
            },
            'components': status.components,
            'performance': status.performance_summary,
            'configuration': status.configuration_summary,
            'errors': status.error_summary
        }
        
        # Add version and build info
        info['version'] = {
            'name': 'PowerTrader AI',
            'version': '1.0.0',
            'build_date': datetime.now().isoformat(),
            'python_version': sys.version
        }
        
        return info
    
    def run_trading_strategy_test(self, strategy_func: Callable,
                                 periods: int = 100) -> Dict[str, Any]:
        """
        Run a trading strategy test with generated market data.
        
        Args:
            strategy_func: Trading strategy function
            periods: Number of periods of market data to generate
            
        Returns:
            Test results and performance metrics
        """
        if not self.is_running:
            raise PowerTraderError("System is not running")
        
        try:
            with PerformanceTimer("strategy_test", self.logger.get_logger() if self.logger else None):
                # Create strategy tester
                tester = TradingStrategyTester()
                
                # Generate market data
                from pt_testing import MarketDataGenerator
                data_generator = MarketDataGenerator()
                market_data = data_generator.generate_ohlcv(periods)
                
                # Run test
                result = tester.run_strategy_test(
                    strategy_func, 
                    market_data, 
                    "User Strategy Test"
                )
                
                # Generate report
                report = tester.generate_test_report()
                
                # Log results
                if self.logger:
                    self.logger.log_audit("strategy_test_completed", details={
                        'test_name': result.test_name,
                        'passed': result.passed,
                        'duration_ms': result.duration_ms,
                        'metrics': result.metrics
                    })
                
                return {
                    'test_result': {
                        'name': result.test_name,
                        'passed': result.passed,
                        'duration_ms': result.duration_ms,
                        'error': result.error_message,
                        'metrics': result.metrics
                    },
                    'report': report
                }
                
        except Exception as e:
            if self.error_handler:
                self.error_handler.handle_error(e, {
                    'operation': 'strategy_test',
                    'periods': periods
                })
            raise
    
    def add_shutdown_handler(self, handler: Callable) -> None:
        """Add a function to call during system shutdown."""
        self.shutdown_handlers.append(handler)
    
    def shutdown(self) -> None:
        """Gracefully shutdown the PowerTrader AI system."""
        if not self.is_running:
            return
        
        print("Shutting down PowerTrader AI...")
        self.status.status = "stopping"
        self.is_running = False
        
        try:
            # Call shutdown handlers
            for handler in self.shutdown_handlers:
                try:
                    handler()
                except Exception as e:
                    print(f"Error in shutdown handler: {e}")
            
            # Stop health monitoring
            if self.health_check_thread:
                self.health_check_thread.join(timeout=5.0)
            
            # Shutdown components
            if self.config_manager:
                self.config_manager.stop()
            
            if self.performance_monitor:
                cleanup_performance_monitoring()
            
            # Log shutdown
            if self.logger:
                self.logger.log_audit("system_shutdown")
                shutdown_logging()
            
            self.status.status = "stopped"
            print("PowerTrader AI shutdown complete")
            
        except Exception as e:
            print(f"Error during shutdown: {e}")
            self.status.status = "error"
            self.status.last_error = str(e)
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown()

# Global system instance
system = PowerTraderSystem()

def main():
    """Main entry point for PowerTrader AI."""
    try:
        # Start system
        if not system.start():
            print("Failed to start PowerTrader AI")
            sys.exit(1)
        
        # Print system info
        info = system.get_system_info()
        print(f"\\nPowerTrader AI {info['version']['version']} is running")
        print(f"Uptime: {info['system']['uptime_seconds']:.1f} seconds")
        print(f"Status: {info['system']['status']}")
        
        # Keep running until interrupted
        try:
            while system.is_running:
                threading.Event().wait(1.0)
        except KeyboardInterrupt:
            pass
        
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
    
    finally:
        system.shutdown()

if __name__ == "__main__":
    main()