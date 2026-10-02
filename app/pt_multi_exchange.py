"""
Exchange Configuration and Management System
Handles multi-exchange setup, credentials, and region-based selection
"""

import json
import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from pt_exchange_abstraction import (
    ConnectionStatus,
    ConnectionTestResult,
    ExchangeFactory,
    ExchangeManager,
    ExchangeType,
)
from pt_exchanges import *


EXAMPLE_CONFIG_NAME = "trading_config.example.json"


@dataclass
class ExchangeConfig:
    """Configuration for a single exchange"""

    exchange_type: str
    enabled: bool
    region_preference: int  # 1=primary, 2=secondary, etc.
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""  # For KuCoin
    sandbox: bool = False


@dataclass
class TradingConfig:
    """Complete trading configuration"""

    user_region: str  # US, EU, UK, GLOBAL
    primary_exchange: str
    exchanges: List[ExchangeConfig]
    price_comparison_enabled: bool = True
    auto_best_price: bool = False


class ExchangeConfigManager:
    """Manages exchange configuration and credentials"""

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = os.path.dirname(os.path.abspath(__file__))

        # trading_config.json holds API keys in plain text and is git-ignored; a
        # fresh clone only has the example, which load_config falls back to.
        self.config_file = os.path.join(config_dir, "trading_config.json")
        self.example_file = os.path.join(config_dir, EXAMPLE_CONFIG_NAME)
        self.config: Optional[TradingConfig] = None

    def load_config(self) -> Optional[TradingConfig]:
        """Load trading configuration.

        Reads ``trading_config.json``. If that file does not exist (a fresh
        clone) the committed example is used instead, so there is always a
        config to edit; the real file is only created by ``save_config``. A
        real file that exists but cannot be read is NOT replaced by the example
        (that would hide the problem and a later save would overwrite it).
        """
        for path in (self.config_file, self.example_file):
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r") as f:
                    data = json.load(f)

                exchanges = [ExchangeConfig(**ex) for ex in data.get("exchanges", [])]

                self.config = TradingConfig(
                    user_region=data.get("user_region", "GLOBAL"),
                    primary_exchange=data.get("primary_exchange", ""),
                    exchanges=exchanges,
                    price_comparison_enabled=data.get("price_comparison_enabled", True),
                    auto_best_price=data.get("auto_best_price", False),
                )
                return self.config
            except Exception as e:
                print(f"Error loading config: {e}")
                return None

        return None

    def save_config(self, config: TradingConfig):
        """Save trading configuration to file"""
        self.config = config

        data = {
            "user_region": config.user_region,
            "primary_exchange": config.primary_exchange,
            "exchanges": [asdict(ex) for ex in config.exchanges],
            "price_comparison_enabled": config.price_comparison_enabled,
            "auto_best_price": config.auto_best_price,
        }

        with open(self.config_file, "w") as f:
            json.dump(data, f, indent=2)

    def create_default_config(self, user_region: str = "GLOBAL") -> TradingConfig:
        """Create default configuration based on user region"""
        exchanges = []
        primary = ""

        if user_region.upper() in ["US", "USA"]:
            # US users - Robinhood, Coinbase, global exchanges
            exchanges = [
                ExchangeConfig("robinhood", False, 1),
                ExchangeConfig("coinbase", False, 2),
                ExchangeConfig("kraken", False, 3),
                ExchangeConfig("binance", False, 4),
                ExchangeConfig("kucoin", False, 5),
            ]
            primary = ""

        elif user_region.upper() in ["EU", "EUROPE"]:
            # EU users - Kraken, Bitstamp, global exchanges
            exchanges = [
                ExchangeConfig("kraken", True, 1),
                ExchangeConfig("binance", True, 2),
                ExchangeConfig("coinbase", True, 3),
                ExchangeConfig("kucoin", False, 4),
                ExchangeConfig("bitstamp", False, 5),
            ]
            primary = "kraken"

        elif user_region.upper() == "UK":
            # UK users - Similar to EU but different preferences
            exchanges = [
                ExchangeConfig("kraken", True, 1),
                ExchangeConfig("coinbase", True, 2),
                ExchangeConfig("binance", True, 3),
                ExchangeConfig("kucoin", False, 4),
            ]
            primary = "kraken"

        else:
            # Global users - All exchanges available
            exchanges = [
                ExchangeConfig("binance", True, 1),
                ExchangeConfig("kraken", True, 2),
                ExchangeConfig("kucoin", True, 3),
                ExchangeConfig("coinbase", False, 4),
                ExchangeConfig("robinhood", False, 5),
            ]
            primary = "binance"

        config = TradingConfig(
            user_region=user_region, primary_exchange=primary, exchanges=exchanges
        )

        self.save_config(config)
        return config

    def get_enabled_exchanges(self) -> List[ExchangeConfig]:
        """Get list of enabled exchange configurations"""
        if not self.config:
            return []

        return [ex for ex in self.config.exchanges if ex.enabled]

    def get_exchange_config(self, exchange_name: str) -> Optional[ExchangeConfig]:
        """Get configuration for specific exchange"""
        if not self.config:
            return None

        for ex in self.config.exchanges:
            if ex.exchange_type == exchange_name:
                return ex

        return None

    def update_exchange_credentials(
        self, exchange_name: str, api_key: str, api_secret: str, passphrase: str = ""
    ):
        """Update credentials for an exchange"""
        if not self.config:
            return

        for ex in self.config.exchanges:
            if ex.exchange_type == exchange_name:
                ex.api_key = api_key
                ex.api_secret = api_secret
                ex.passphrase = passphrase
                break

        self.save_config(self.config)

    def enable_exchange(self, exchange_name: str, enabled: bool = True):
        """Enable or disable an exchange"""
        if not self.config:
            return

        for ex in self.config.exchanges:
            if ex.exchange_type == exchange_name:
                ex.enabled = enabled
                break

        self.save_config(self.config)


class MultiExchangeManager:
    """High-level manager for multiple exchange operations"""

    def __init__(self, config_manager: ExchangeConfigManager = None):
        self.config_manager = config_manager or ExchangeConfigManager()
        self.exchange_manager = ExchangeManager()
        self.initialized = False

    def initialize(self, user_region: str = None) -> bool:
        """Initialize exchange connections based on configuration"""
        # Load or create configuration
        config = self.config_manager.load_config()
        if not config and user_region:
            config = self.config_manager.create_default_config(user_region)
        elif not config:
            print(
                "No configuration found. Please set user_region or create config manually."
            )
            return False

        # Connect to enabled exchanges
        enabled_exchanges = self.config_manager.get_enabled_exchanges()
        success_count = 0

        for exchange_config in enabled_exchanges:
            try:
                exchange_type = ExchangeType(exchange_config.exchange_type)

                # Get credentials from config or environment
                credentials = self._get_exchange_credentials(exchange_config)

                # For public market data, allow connections without credentials
                if not credentials:
                    print(
                        f"No credentials for {exchange_config.exchange_type}, trying public access..."
                    )
                    credentials = {}

                # Add exchange to manager
                if self.exchange_manager.add_exchange(exchange_type, **credentials):
                    success_count += 1
                    print(f"[SUCCESS] Connected to {exchange_config.exchange_type}")
                else:
                    print(
                        f"[ERROR] Failed to connect to {exchange_config.exchange_type}"
                    )

            except Exception as e:
                print(f"Error connecting to {exchange_config.exchange_type}: {e}")

        # Set primary exchange
        if config.primary_exchange and success_count > 0:
            try:
                primary_type = ExchangeType(config.primary_exchange)
                self.exchange_manager.set_primary_exchange(primary_type)
                print(f"Primary exchange: {config.primary_exchange}")
            except Exception as e:
                print(f"Could not set primary exchange: {e}")

        self.initialized = success_count > 0
        return self.initialized

    def get_current_price(self, symbol: str, exchange_name: str = None) -> float:
        """Get current price from specific exchange or primary"""
        if not self.initialized:
            raise RuntimeError("MultiExchangeManager not initialized")

        if exchange_name:
            exchange_type = ExchangeType(exchange_name)
            return self.exchange_manager.get_current_price(symbol, exchange_type)
        else:
            return self.exchange_manager.get_current_price(symbol)

    def compare_prices(self, symbol: str) -> Dict[str, float]:
        """Compare prices across all connected exchanges"""
        if not self.initialized:
            raise RuntimeError("MultiExchangeManager not initialized")

        prices = {}
        for exchange_type, exchange in self.exchange_manager.exchanges.items():
            try:
                price = exchange.get_current_price(symbol)
                prices[exchange_type.value] = price
            except Exception as e:
                print(f"Error getting price from {exchange_type.value}: {e}")

        return prices

    def get_best_price(self, symbol: str, side: str = "buy") -> tuple:
        """Get best price across all exchanges"""
        if not self.initialized:
            raise RuntimeError("MultiExchangeManager not initialized")

        return self.exchange_manager.get_best_price(symbol, side)

    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        exchange_name: str = None,
    ):
        """Place order on specific exchange or primary"""
        if not self.initialized:
            raise RuntimeError("MultiExchangeManager not initialized")

        if exchange_name:
            exchange_type = ExchangeType(exchange_name)
            return self.exchange_manager.place_order(
                symbol, side, amount, price, exchange_type
            )
        else:
            return self.exchange_manager.place_order(symbol, side, amount, price)

    def test_exchange_connection(
        self,
        exchange_name: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
    ) -> ConnectionTestResult:
        """Check credentials with one read-only authenticated call.

        ``api_key``/``api_secret``/``passphrase`` are used as given (e.g. what is
        typed in the setup form) and are NOT saved. When both ``api_key`` and
        ``api_secret`` are omitted the stored credentials (config file, then
        ``POWERTRADER_<EXCHANGE>_*`` environment variables) are used. Never places,
        previews or cancels an order, and never raises for a bad connection: the
        outcome is in ``ConnectionTestResult.status``.
        """
        name = (exchange_name or "").strip().lower()
        try:
            exchange_type = ExchangeType(name)
        except ValueError:
            return ConnectionTestResult(
                name,
                ConnectionStatus.UNSUPPORTED,
                f"'{exchange_name}' is not an exchange PowerTrader can connect to.",
            )

        exchange_class = ExchangeFactory.get_exchange_class(exchange_type)
        if exchange_class is None:
            return ConnectionTestResult(
                name,
                ConnectionStatus.UNSUPPORTED,
                f"{name.title()} has no connector in this version of PowerTrader, so "
                "its credentials cannot be tested.",
            )

        if api_key is None and api_secret is None:
            creds = self._stored_credentials(name)
        else:
            creds = {"api_key": api_key or "", "api_secret": api_secret or ""}
            if passphrase:
                creds["passphrase"] = passphrase
        if not creds or not creds.get("api_key") or not creds.get("api_secret"):
            return ConnectionTestResult(
                name,
                ConnectionStatus.INVALID_CREDENTIALS,
                f"No {name.title()} credentials were entered or saved.",
            )

        try:
            exchange = exchange_class(**creds)
            return exchange.check_connection()
        except Exception as exc:  # a connector bug must not take the GUI down
            return ConnectionTestResult(
                name,
                ConnectionStatus.ENDPOINT_ERROR,
                f"The {name.title()} connection test failed unexpectedly "
                f"({type(exc).__name__}).",
            )

    def _stored_credentials(self, exchange_name: str) -> Optional[Dict[str, str]]:
        if self.config_manager.config is None:
            self.config_manager.load_config()
        exchange_config = self.config_manager.get_exchange_config(exchange_name)
        if exchange_config is not None:
            return self._get_exchange_credentials(exchange_config)
        return self._get_exchange_credentials(ExchangeConfig(exchange_name, False, 0))

    def get_available_exchanges(self) -> List[str]:
        """Get list of connected exchanges"""
        if not self.initialized:
            return []

        return [ex.value for ex in self.exchange_manager.exchanges.keys()]

    def _get_exchange_credentials(
        self, exchange_config: ExchangeConfig
    ) -> Optional[Dict[str, str]]:
        """Get credentials for exchange from config or environment"""
        # Check config first
        if exchange_config.api_key and exchange_config.api_secret:
            creds = {
                "api_key": exchange_config.api_key,
                "api_secret": exchange_config.api_secret,
            }
            if exchange_config.passphrase:
                creds["passphrase"] = exchange_config.passphrase
            return creds

        # Check environment variables
        exchange_name = exchange_config.exchange_type.upper()
        api_key = os.environ.get(f"POWERTRADER_{exchange_name}_API_KEY")
        api_secret = os.environ.get(f"POWERTRADER_{exchange_name}_API_SECRET")

        if api_key and api_secret:
            creds = {"api_key": api_key, "api_secret": api_secret}

            # Check for passphrase (KuCoin)
            passphrase = os.environ.get(f"POWERTRADER_{exchange_name}_PASSPHRASE")
            if passphrase:
                creds["passphrase"] = passphrase

            return creds

        return None


# Global instance for easy access
multi_exchange_manager = MultiExchangeManager()
