"""
Exchange Configuration and Management System
Handles multi-exchange setup, credentials, and region-based selection
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pt_paths
import pt_secrets
from pt_exchange_abstraction import (
    ConnectionStatus,
    ConnectionTestResult,
    ExchangeFactory,
    ExchangeManager,
    ExchangeType,
)
from pt_exchanges import *

logger = logging.getLogger("pt_multi_exchange")

EXAMPLE_CONFIG_NAME = "trading_config.example.json"

# ExchangeConfig attributes that are credentials: kept in the OS keyring through
# pt_secrets, never in trading_config.json.
CREDENTIAL_ATTRS = ("api_key", "api_secret", "passphrase")


@dataclass
class ExchangeConfig:
    """Configuration for a single exchange.

    ``api_key``/``api_secret``/``passphrase`` are filled in memory from
    ``pt_secrets`` when the config is loaded and are never written to the
    config file; ``repr`` never shows them.
    """

    exchange_type: str
    enabled: bool
    region_preference: int  # 1=primary, 2=secondary, etc.
    api_key: str = field(default="", repr=False)
    api_secret: str = field(default="", repr=False)
    passphrase: str = field(default="", repr=False)  # For KuCoin
    sandbox: bool = False
    # Where the credentials above came from ("environment", "keyring" or "").
    credential_source: str = field(default="", repr=False, compare=False)


# The ExchangeConfig attributes written to trading_config.json.
_FILE_FIELDS = ("exchange_type", "enabled", "region_preference", "sandbox")


def _fill_credentials(ex: ExchangeConfig) -> None:
    """Set ``ex``'s credential attributes from pt_secrets (environment, then keyring)."""
    try:
        creds = pt_secrets.get_credentials(ex.exchange_type)
    except pt_secrets.SecretsError:
        creds = None
    for attr in CREDENTIAL_ATTRS:
        setattr(ex, attr, (creds or {}).get(attr, ""))
    ex.credential_source = creds.source if creds else ""


@dataclass
class TradingConfig:
    """Complete trading configuration"""

    user_region: str  # US, EU, UK, GLOBAL
    primary_exchange: str
    exchanges: List[ExchangeConfig]
    price_comparison_enabled: bool = True
    auto_best_price: bool = False


def _credential_field(exchange: str, attr: str) -> Optional[str]:
    """pt_secrets field behind an ExchangeConfig credential attribute
    (Coinbase ``api_key`` -> ``key_name``), or None if the exchange has none."""
    try:
        return pt_secrets.field_for_kwarg(exchange, attr)
    except pt_secrets.SecretsError:
        return None


class ExchangeConfigManager:
    """Manages exchange configuration. Credentials go through ``pt_secrets``:
    the config file holds no secret, the in-memory ``ExchangeConfig`` objects
    carry the credentials read from the environment or the OS keyring."""

    def __init__(self, config_dir: str = None):
        # Default: the user config folder, falling back to the read-only template
        # shipped in the program folder. An explicit folder uses its own example.
        if config_dir is None:
            config_dir = pt_paths.config_dir()
            self.example_file = pt_paths.shipped_default(EXAMPLE_CONFIG_NAME)
        else:
            self.example_file = os.path.join(config_dir, EXAMPLE_CONFIG_NAME)
        self.config_file = os.path.join(config_dir, pt_paths.TRADING_CONFIG_FILE)
        self.config: Optional[TradingConfig] = None

    def load_config(self) -> Optional[TradingConfig]:
        """Load trading configuration.

        Reads ``trading_config.json``. If that file does not exist (a fresh
        clone) the committed example is used instead, so there is always a
        config to edit; the real file is only created by ``save_config``. A
        real file that exists but cannot be read is NOT replaced by the example
        (that would hide the problem and a later save would overwrite it).

        Credential fields found in the file are ignored (with a warning) and
        never written back; credentials come from ``pt_secrets``.
        """
        for path in (self.config_file, self.example_file):
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                exchanges = [
                    self._exchange_from_file(ex, path) for ex in data.get("exchanges", [])
                ]

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

    @staticmethod
    def _exchange_from_file(raw: dict, path: str) -> ExchangeConfig:
        settings = {}
        for key, value in raw.items():
            if pt_secrets.is_secret_key(key):
                if value:
                    logger.warning(
                        "%s holds a credential field (%s.%s); it is ignored and will "
                        "not be written back. Re-enter it in the exchange setup window "
                        "or run the migration (pt_migrate.py).",
                        os.path.basename(path),
                        raw.get("exchange_type", "?"),
                        key,
                    )
                continue
            if key in _FILE_FIELDS:
                settings[key] = value
        ex = ExchangeConfig(**settings)
        _fill_credentials(ex)
        return ex

    def save_config(self, config: TradingConfig):
        """Save trading configuration: settings to the file, credentials to the
        OS keyring (``pt_secrets``). Raises ``pt_secrets.KeyringUnavailable``
        (after saving the settings) when credentials cannot be stored securely."""
        self.config = config

        data = {
            "user_region": config.user_region,
            "primary_exchange": config.primary_exchange,
            "exchanges": [
                {key: getattr(ex, key) for key in _FILE_FIELDS} for ex in config.exchanges
            ],
            "price_comparison_enabled": config.price_comparison_enabled,
            "auto_best_price": config.auto_best_price,
        }

        pt_paths.write_private_text(self.config_file, json.dumps(data, indent=2))

        for ex in config.exchanges:
            if ex.credential_source == pt_secrets.SOURCE_ENV:
                continue  # never copy environment credentials into the keyring
            values = {}
            for attr in CREDENTIAL_ATTRS:
                name = _credential_field(ex.exchange_type, attr)
                if name and getattr(ex, attr):
                    values[name] = getattr(ex, attr)
            if values:
                pt_secrets.set_credentials(ex.exchange_type, values)
                ex.credential_source = pt_secrets.SOURCE_KEYRING

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
        """Store credentials for an exchange in the OS keyring (empty values
        remove them). Raises ``pt_secrets.KeyringUnavailable`` /
        ``pt_secrets.SecretTooLarge`` without storing anything."""
        if not self.config:
            return

        given = {"api_key": api_key, "api_secret": api_secret, "passphrase": passphrase}
        values = {}
        for attr, value in given.items():
            name = _credential_field(exchange_name, attr)
            if name:
                values[name] = value or ""
        pt_secrets.set_credentials(exchange_name, values)

        ex = self.get_exchange_config(exchange_name)
        if ex is None:
            ex = ExchangeConfig(exchange_name, False, len(self.config.exchanges) + 1)
            self.config.exchanges.append(ex)
        _fill_credentials(ex)
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
        """Credentials for the exchange from ``pt_secrets`` (environment first,
        then the OS keyring) -- the same source the live gate uses."""
        try:
            return pt_secrets.get_credentials(exchange_config.exchange_type)
        except pt_secrets.SecretsError:
            return None


# Global instance for easy access
multi_exchange_manager = MultiExchangeManager()
