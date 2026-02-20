import os
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Also add app directory specifically
app_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"
)
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)


@pytest.fixture
def mock_kucoin_data():
    """Mock KuCoin market data for testing"""
    return {
        "symbol": "BTC-USDT",
        "price": "50000.00",
        "volume": "1000.5",
        "change": "2.5",
        "timestamp": datetime.now().isoformat(),
    }


@pytest.fixture
def mock_robinhood_auth():
    """Mock Robinhood authentication for testing"""
    with patch("robin_stocks.robinhood.authentication.login") as mock_login:
        mock_login.return_value = {"access_token": "test_token"}
        yield mock_login


@pytest.fixture
def trading_config():
    """Sample trading configuration for tests"""
    return {
        "max_investment": 1000.0,
        "risk_tolerance": 0.05,
        "stop_loss": 0.10,
        "take_profit": 0.15,
        "trading_pairs": ["BTC-USDT", "ETH-USDT"],
    }


@pytest.fixture(scope="session")
def test_environment():
    """Set up test environment variables"""
    os.environ["POWERTRADER_ENV"] = "test"
    os.environ["POWERTRADER_LOG_LEVEL"] = "DEBUG"
    yield
    # Cleanup
    os.environ.pop("POWERTRADER_ENV", None)
    os.environ.pop("POWERTRADER_LOG_LEVEL", None)
