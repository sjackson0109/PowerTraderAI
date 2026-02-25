#!/usr/bin/env python3
"""
Production Deployment Configuration for PowerTrader
Handles production environment setup, monitoring, and deployment
"""

import configparser
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


class ProductionConfig:
    """Production configuration management"""

    def __init__(self, config_dir="config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)

        self.config_file = self.config_dir / "production.ini"
        self.secrets_file = self.config_dir / "secrets.json"

        self.config = configparser.ConfigParser()
        self._load_config()

    def _load_config(self):
        """Load production configuration"""

        # Create default config if it doesn't exist
        if not self.config_file.exists():
            self._create_default_config()

        self.config.read(self.config_file)

    def _create_default_config(self):
        """Create default production configuration"""

        default_config = {
            "application": {
                "name": "PowerTraderAI+",
                "version": "3.0.0",
                "environment": "production",
                "debug": "false",
                "log_level": "INFO",
            },
            "security": {
                "require_authentication": "true",
                "session_timeout": "3600",  # 1 hour
                "max_login_attempts": "5",
                "enable_audit_log": "true",
            },
            "performance": {
                "max_memory_usage_mb": "1024",
                "max_cpu_usage_percent": "80",
                "connection_timeout": "30",
                "request_timeout": "60",
            },
            "monitoring": {
                "enable_health_checks": "true",
                "health_check_interval": "300",  # 5 minutes
                "enable_metrics": "true",
                "metrics_retention_days": "30",
            },
            "data": {
                "cache_enabled": "true",
                "cache_size_mb": "256",
                "data_backup_enabled": "true",
                "backup_interval_hours": "24",
            },
            "alerts": {
                "enable_email_alerts": "false",
                "enable_system_alerts": "true",
                "alert_thresholds_file": "alert_thresholds.json",
            },
        }

        # Write default configuration
        for section, options in default_config.items():
            self.config.add_section(section)
            for key, value in options.items():
                self.config.set(section, key, value)

        with open(self.config_file, "w") as f:
            self.config.write(f)

        print(f"Created default production configuration: {self.config_file}")

    def get(self, section, option, fallback=None):
        """Get configuration value"""
        return self.config.get(section, option, fallback=fallback)

    def getboolean(self, section, option, fallback=None):
        """Get boolean configuration value"""
        return self.config.getboolean(section, option, fallback=fallback)

    def getint(self, section, option, fallback=None):
        """Get integer configuration value"""
        return self.config.getint(section, option, fallback=fallback)


class ProductionLogger:
    """Production logging setup"""

    def __init__(self, config):
        self.config = config
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)

        self._setup_logging()

    def _setup_logging(self):
        """Set up production logging"""

        log_level = getattr(
            logging, self.config.get("application", "log_level", "INFO")
        )

        # Create formatters
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"
        )
        console_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )

        # Set up root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        # Clear existing handlers
        root_logger.handlers = []

        # Add file handler
        log_file = self.log_dir / f"powertrader_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        # Add console handler for non-production or when debug is enabled
        if self.config.getboolean("application", "debug", False):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level)
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)

        # Set up audit logger
        audit_logger = logging.getLogger("audit")
        audit_file = self.log_dir / f"audit_{datetime.now().strftime('%Y%m%d')}.log"
        audit_handler = logging.FileHandler(audit_file)
        audit_handler.setLevel(logging.INFO)
        audit_handler.setFormatter(file_formatter)
        audit_logger.addHandler(audit_handler)

        logging.info("Production logging initialized")


class HealthMonitor:
    """System health monitoring"""

    def __init__(self, config):
        self.config = config
        self.metrics = {}
        self.alerts = []

        self.start_time = datetime.now()

        # Load alert thresholds
        self._load_alert_thresholds()

    def _load_alert_thresholds(self):
        """Load alert thresholds configuration"""

        default_thresholds = {
            "max_memory_mb": self.config.getint(
                "performance", "max_memory_usage_mb", 1024
            ),
            "max_cpu_percent": self.config.getint(
                "performance", "max_cpu_usage_percent", 80
            ),
            "max_response_time_ms": 5000,
            "min_available_disk_gb": 1,
            "max_error_rate_percent": 5,
        }

        thresholds_file = self.config.config_dir / "alert_thresholds.json"

        if thresholds_file.exists():
            try:
                with open(thresholds_file, "r") as f:
                    self.thresholds = json.load(f)
            except Exception as e:
                logging.warning(f"Could not load alert thresholds: {e}")
                self.thresholds = default_thresholds
        else:
            self.thresholds = default_thresholds

            # Save default thresholds
            with open(thresholds_file, "w") as f:
                json.dump(default_thresholds, f, indent=2)

    def check_system_health(self):
        """Check system health and return status"""

        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "checks": {},
        }

        # Check memory usage
        try:
            import psutil

            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            cpu_percent = process.cpu_percent()

            health_status["checks"]["memory"] = {
                "status": "ok"
                if memory_mb < self.thresholds["max_memory_mb"]
                else "warning",
                "value_mb": round(memory_mb, 1),
                "threshold_mb": self.thresholds["max_memory_mb"],
            }

            health_status["checks"]["cpu"] = {
                "status": "ok"
                if cpu_percent < self.thresholds["max_cpu_percent"]
                else "warning",
                "value_percent": round(cpu_percent, 1),
                "threshold_percent": self.thresholds["max_cpu_percent"],
            }

            # Overall system status
            system_usage = psutil.virtual_memory()
            disk_usage = psutil.disk_usage("/")

            health_status["checks"]["system_memory"] = {
                "status": "ok" if system_usage.percent < 90 else "warning",
                "used_percent": system_usage.percent,
            }

            health_status["checks"]["disk"] = {
                "status": "ok"
                if disk_usage.free / (1024**3)
                > self.thresholds["min_available_disk_gb"]
                else "warning",
                "free_gb": round(disk_usage.free / (1024**3), 1),
            }

        except ImportError:
            health_status["checks"]["system"] = {
                "status": "unknown",
                "message": "psutil not available for system monitoring",
            }
        except Exception as e:
            health_status["checks"]["system"] = {"status": "error", "message": str(e)}

        # Check application health
        health_status["checks"]["application"] = self._check_application_health()

        # Determine overall status
        check_statuses = [
            check.get("status", "unknown") for check in health_status["checks"].values()
        ]

        if "error" in check_statuses:
            health_status["status"] = "unhealthy"
        elif "warning" in check_statuses:
            health_status["status"] = "degraded"

        # Log health status
        if health_status["status"] != "healthy":
            logging.warning(f"System health check: {health_status['status']}")

        return health_status

    def _check_application_health(self):
        """Check application-specific health"""

        try:
            # Try importing core modules
            import pt_hub

            # Check if GUI can be imported
            try:
                from portfolio_optimizer import PortfolioOptimizer

                portfolio_ok = True
            except ImportError:
                portfolio_ok = False

            try:
                from backtesting_engine import BacktestEngine

                backtesting_ok = True
            except ImportError:
                backtesting_ok = False

            try:
                from performance_attribution import PerformanceAttributionEngine

                attribution_ok = True
            except ImportError:
                attribution_ok = False

            return {
                "status": "ok",
                "core_modules": "loaded",
                "advanced_features": {
                    "portfolio_optimization": portfolio_ok,
                    "backtesting": backtesting_ok,
                    "performance_attribution": attribution_ok,
                },
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def log_metric(self, name, value, tags=None):
        """Log a metric value"""

        timestamp = datetime.now()

        if name not in self.metrics:
            self.metrics[name] = []

        self.metrics[name].append(
            {"timestamp": timestamp, "value": value, "tags": tags or {}}
        )

        # Keep only recent metrics (configurable retention)
        retention_days = self.config.getint("monitoring", "metrics_retention_days", 30)
        cutoff_time = timestamp - timedelta(days=retention_days)

        self.metrics[name] = [
            m for m in self.metrics[name] if m["timestamp"] > cutoff_time
        ]

    def get_metrics_summary(self):
        """Get summary of all metrics"""

        summary = {}

        for name, values in self.metrics.items():
            if not values:
                continue

            recent_values = [m["value"] for m in values[-100:]]  # Last 100 values

            summary[name] = {
                "count": len(values),
                "latest": values[-1]["value"] if values else None,
                "average": sum(recent_values) / len(recent_values)
                if recent_values
                else 0,
                "min": min(recent_values) if recent_values else 0,
                "max": max(recent_values) if recent_values else 0,
            }

        return summary


class ProductionDeployment:
    """Production deployment management"""

    def __init__(self):
        self.config = ProductionConfig()
        self.logger = ProductionLogger(self.config)
        self.monitor = HealthMonitor(self.config)

        logging.info("PowerTrader Production Environment initialized")

    def validate_environment(self):
        """Validate production environment requirements"""

        validation_results = {"valid": True, "checks": {}, "warnings": [], "errors": []}

        # Check Python version
        python_version = sys.version_info
        if python_version < (3, 8):
            validation_results["errors"].append(
                f"Python {python_version.major}.{python_version.minor} too old, need 3.8+"
            )
            validation_results["valid"] = False

        validation_results["checks"][
            "python_version"
        ] = f"{python_version.major}.{python_version.minor}.{python_version.micro}"

        # Check required directories
        required_dirs = ["logs", "config", "data", "backups"]
        for dir_name in required_dirs:
            dir_path = Path(dir_name)
            if not dir_path.exists():
                dir_path.mkdir(exist_ok=True)
                validation_results["warnings"].append(
                    f"Created missing directory: {dir_name}"
                )

        # Check disk space
        try:
            import psutil

            disk_usage = psutil.disk_usage("/")
            free_gb = disk_usage.free / (1024**3)

            if free_gb < 1:
                validation_results["errors"].append(
                    f"Insufficient disk space: {free_gb:.1f} GB free"
                )
                validation_results["valid"] = False
            elif free_gb < 5:
                validation_results["warnings"].append(
                    f"Low disk space: {free_gb:.1f} GB free"
                )

            validation_results["checks"]["disk_space_gb"] = round(free_gb, 1)

        except ImportError:
            validation_results["warnings"].append(
                "Cannot check disk space (psutil not available)"
            )

        # Check core dependencies
        core_dependencies = ["tkinter", "json", "csv", "datetime"]
        for dep in core_dependencies:
            try:
                __import__(dep)
                validation_results["checks"][f"dependency_{dep}"] = "available"
            except ImportError:
                validation_results["errors"].append(f"Missing core dependency: {dep}")
                validation_results["valid"] = False

        # Check optional dependencies
        optional_dependencies = ["pandas", "numpy", "scipy", "matplotlib"]
        available_optional = []

        for dep in optional_dependencies:
            try:
                __import__(dep)
                available_optional.append(dep)
            except ImportError:
                pass

        validation_results["checks"]["optional_dependencies"] = available_optional

        if len(available_optional) == 0:
            validation_results["warnings"].append(
                "No optional dependencies available - advanced features will be limited"
            )

        return validation_results

    def start_monitoring(self):
        """Start production monitoring"""

        if not self.config.getboolean("monitoring", "enable_health_checks", True):
            logging.info("Health monitoring disabled")
            return

        interval = self.config.getint("monitoring", "health_check_interval", 300)

        logging.info(f"Starting health monitoring (interval: {interval}s)")

        # Initial health check
        health_status = self.monitor.check_system_health()
        logging.info(f"Initial health status: {health_status['status']}")

        # In a real production environment, this would run in a separate thread
        # For now, just return the monitoring setup
        return {
            "monitoring_enabled": True,
            "interval_seconds": interval,
            "initial_health": health_status,
        }

    def create_deployment_package(self):
        """Create deployment package"""

        package_info = {
            "name": "powertrader-production",
            "version": self.config.get("application", "version"),
            "created": datetime.now().isoformat(),
            "environment": "production",
        }

        # Create deployment structure
        deployment_dir = Path("deployment")
        deployment_dir.mkdir(exist_ok=True)

        # Copy configuration files
        config_dest = deployment_dir / "config"
        config_dest.mkdir(exist_ok=True)

        # Create startup script
        startup_script = deployment_dir / "start_powertrader.py"

        startup_content = '''#!/usr/bin/env python3
"""
PowerTrader Production Startup Script
"""

import sys
import os
from pathlib import Path

# Add app directory to Python path
app_dir = Path(__file__).parent / 'app'
sys.path.insert(0, str(app_dir))

def main():
    """Start PowerTrader in production mode"""

    print("Starting PowerTrader in production mode...")

    try:
        from production_deployment import ProductionDeployment

        # Initialize production environment
        deployment = ProductionDeployment()

        # Validate environment
        validation = deployment.validate_environment()

        if not validation['valid']:
            print("Environment validation failed:")
            for error in validation['errors']:
                print(f"  - {error}")
            return 1

        if validation['warnings']:
            print("Environment warnings:")
            for warning in validation['warnings']:
                print(f"  - {warning}")

        # Start monitoring
        monitoring = deployment.start_monitoring()
        print(f"Monitoring started: {monitoring['monitoring_enabled']}")

        # Start PowerTrader Hub
        from pt_hub import PowerTraderHub

        print("Starting PowerTrader Hub...")
        app = PowerTraderHub()
        app.mainloop()

    except ImportError as e:
        print(f"Import error: {e}")
        return 1
    except Exception as e:
        print(f"Startup error: {e}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
'''

        with open(startup_script, "w", encoding="utf-8") as f:
            f.write(startup_content)

        # Make startup script executable
        try:
            os.chmod(startup_script, 0o755)
        except:
            pass  # Windows doesn't use chmod

        # Create package info file
        package_file = deployment_dir / "package.json"
        with open(package_file, "w") as f:
            json.dump(package_info, f, indent=2)

        logging.info(f"Deployment package created: {deployment_dir}")

        return {
            "package_dir": str(deployment_dir),
            "package_info": package_info,
            "startup_script": str(startup_script),
        }


def main():
    """Main deployment setup function"""

    print("=" * 60)
    print("PowerTrader Production Deployment Setup")
    print("=" * 60)
    print()

    try:
        # Initialize production deployment
        deployment = ProductionDeployment()

        # Validate environment
        print("🔍 Validating production environment...")
        validation = deployment.validate_environment()

        print(f"✅ Python version: {validation['checks']['python_version']}")
        print(
            f"✅ Disk space: {validation['checks'].get('disk_space_gb', 'unknown')} GB"
        )
        print(
            f"✅ Optional dependencies: {', '.join(validation['checks']['optional_dependencies'])}"
        )

        if validation["warnings"]:
            print("\n⚠️  Warnings:")
            for warning in validation["warnings"]:
                print(f"  - {warning}")

        if validation["errors"]:
            print("\n❌ Errors:")
            for error in validation["errors"]:
                print(f"  - {error}")

            if not validation["valid"]:
                print(
                    "\n🚫 Environment validation failed. Please fix errors before deploying."
                )
                return 1

        # Start monitoring
        print("\n📊 Setting up monitoring...")
        monitoring = deployment.start_monitoring()

        if monitoring["monitoring_enabled"]:
            print(
                f"✅ Health monitoring enabled (interval: {monitoring['interval_seconds']}s)"
            )
            print(f"✅ Initial health: {monitoring['initial_health']['status']}")

        # Create deployment package
        print("\n📦 Creating deployment package...")
        package = deployment.create_deployment_package()

        print(f"✅ Package created: {package['package_dir']}")
        print(f"✅ Startup script: {package['startup_script']}")

        print("\n🎉 Production deployment setup complete!")
        print("\nTo start PowerTrader in production mode:")
        print(f"  python {package['startup_script']}")

        return 0

    except Exception as e:
        print(f"\n❌ Deployment setup failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
