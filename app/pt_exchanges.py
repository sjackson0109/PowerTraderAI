"""
Specific Exchange Implementations
All major cryptocurrency exchanges with unified interface
"""
import base64
import hashlib
import hmac
import json
import time
from typing import Dict, List, Optional

import requests
from pt_exchange_abstraction import (
    AbstractExchange,
    ExchangeType,
    MarketData,
    OrderResult,
)


class RobinhoodExchange(AbstractExchange):
    """Robinhood Crypto Trading API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://trading.robinhood.com"
        self.session = requests.Session()

    def get_exchange_name(self) -> str:
        return "robinhood"

    def get_current_price(self, symbol: str) -> float:
        market_data = self.get_market_data(symbol)
        return market_data.ask

    def get_market_data(self, symbol: str) -> MarketData:
        endpoint = f"/api/v1/crypto/marketdata/best_bid_ask/?symbol={symbol}"
        response = self._make_request("GET", endpoint)

        if not response or "results" not in response or not response["results"]:
            raise RuntimeError(f"No market data for {symbol}")

        result = response["results"][0]
        return MarketData(
            symbol=symbol,
            price=float(result["ask_inclusive_of_buy_spread"]),
            bid=float(result["bid_inclusive_of_sell_spread"]),
            ask=float(result["ask_inclusive_of_buy_spread"]),
            volume=0.0,  # Not provided by this endpoint
            timestamp=time.time(),
            exchange="robinhood",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        # Implement Robinhood order placement
        # This would use the existing pt_trader.py logic
        raise NotImplementedError("Order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        # Implement balance retrieval
        raise NotImplementedError("Balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return region.upper() in ["US", "USA"]

    def _make_request(
        self, method: str, endpoint: str, params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Make authenticated API request to Robinhood"""
        url = self.base_url + endpoint
        timestamp = str(int(time.time()))

        # Create signature (simplified - use existing logic from pt_trader.py)
        try:
            response = self.session.request(method, url, params=params, timeout=10)
            return response.json() if response.status_code == 200 else None
        except Exception:
            return None


class KrakenExchange(AbstractExchange):
    """Kraken API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.kraken.com"

    def get_exchange_name(self) -> str:
        return "kraken"

    def get_current_price(self, symbol: str) -> float:
        # Convert symbol format (BTC-USD -> XBTUSD)
        kraken_symbol = self._convert_symbol(symbol)

        response = requests.get(f"{self.base_url}/0/public/Ticker?pair={kraken_symbol}")
        data = response.json()

        if "error" in data and data["error"]:
            raise RuntimeError(f"Kraken API error: {data['error']}")

        ticker_data = list(data["result"].values())[0]
        return float(ticker_data["a"][0])  # Ask price

    def get_market_data(self, symbol: str) -> MarketData:
        kraken_symbol = self._convert_symbol(symbol)

        response = requests.get(f"{self.base_url}/0/public/Ticker?pair={kraken_symbol}")
        data = response.json()

        if "error" in data and data["error"]:
            raise RuntimeError(f"Kraken API error: {data['error']}")

        ticker_data = list(data["result"].values())[0]

        return MarketData(
            symbol=symbol,
            price=float(ticker_data["c"][0]),  # Last price
            bid=float(ticker_data["b"][0]),  # Bid
            ask=float(ticker_data["a"][0]),  # Ask
            volume=float(ticker_data["v"][0]),  # Volume
            timestamp=time.time(),
            exchange="kraken",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Kraken order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Kraken balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Kraken order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Kraken order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return region.upper() in ["EU", "UK", "EUROPE", "GLOBAL"]

    def _convert_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Kraken format"""
        # BTC-USD -> XBTUSD
        symbol_map = {
            "BTC-USD": "XBTUSD",
            "ETH-USD": "ETHUSD",
            "ADA-USD": "ADAUSD",
            "DOGE-USD": "DOGEUSD",
        }
        return symbol_map.get(symbol, symbol.replace("-", ""))


class BinanceExchange(AbstractExchange):
    """Binance API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.binance.com"

    def get_exchange_name(self) -> str:
        return "binance"

    def get_current_price(self, symbol: str) -> float:
        binance_symbol = self._convert_symbol(symbol)

        response = requests.get(
            f"{self.base_url}/api/v3/ticker/price?symbol={binance_symbol}"
        )
        data = response.json()

        if "code" in data:
            raise RuntimeError(f"Binance API error: {data['msg']}")

        return float(data["price"])

    def get_market_data(self, symbol: str) -> MarketData:
        binance_symbol = self._convert_symbol(symbol)

        # Get ticker data
        ticker_response = requests.get(
            f"{self.base_url}/api/v3/ticker/24hr?symbol={binance_symbol}"
        )
        ticker_data = ticker_response.json()

        # Get order book for bid/ask
        book_response = requests.get(
            f"{self.base_url}/api/v3/ticker/bookTicker?symbol={binance_symbol}"
        )
        book_data = book_response.json()

        return MarketData(
            symbol=symbol,
            price=float(ticker_data["lastPrice"]),
            bid=float(book_data["bidPrice"]),
            ask=float(book_data["askPrice"]),
            volume=float(ticker_data["volume"]),
            timestamp=time.time(),
            exchange="binance",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Binance order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Binance balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Binance order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Binance order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return True  # Available globally (check local regulations)

    def _convert_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Binance format"""
        # BTC-USD -> BTCUSDT
        return symbol.replace("-USD", "USDT").replace("-", "")


class CoinbaseExchange(AbstractExchange):
    """Coinbase Advanced Trade API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.exchange.coinbase.com"

    def get_exchange_name(self) -> str:
        return "coinbase"

    def get_current_price(self, symbol: str) -> float:
        coinbase_symbol = self._convert_symbol(symbol)

        response = requests.get(f"{self.base_url}/products/{coinbase_symbol}/ticker")
        data = response.json()

        if "message" in data:
            raise RuntimeError(f"Coinbase API error: {data['message']}")

        return float(data["ask"])

    def get_market_data(self, symbol: str) -> MarketData:
        coinbase_symbol = self._convert_symbol(symbol)

        response = requests.get(f"{self.base_url}/products/{coinbase_symbol}/ticker")
        data = response.json()

        return MarketData(
            symbol=symbol,
            price=float(data["price"]),
            bid=float(data["bid"]),
            ask=float(data["ask"]),
            volume=float(data["volume"]),
            timestamp=time.time(),
            exchange="coinbase",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Coinbase order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Coinbase balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Coinbase order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Coinbase order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return region.upper() in ["US", "USA", "EU", "UK", "EUROPE"]

    def _convert_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Coinbase format"""
        # BTC-USD -> BTC-USD (same format)
        return symbol


class KuCoinExchange(AbstractExchange):
    """KuCoin API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.kucoin.com"
        self.passphrase = kwargs.get("passphrase", "")

    def get_exchange_name(self) -> str:
        return "kucoin"

    def get_current_price(self, symbol: str) -> float:
        kucoin_symbol = self._convert_symbol(symbol)

        response = requests.get(
            f"{self.base_url}/api/v1/market/orderbook/level1?symbol={kucoin_symbol}"
        )
        data = response.json()

        if data["code"] != "200000":
            raise RuntimeError(f"KuCoin API error: {data['msg']}")

        return float(data["data"]["bestAsk"])

    def get_market_data(self, symbol: str) -> MarketData:
        kucoin_symbol = self._convert_symbol(symbol)

        # Get ticker data
        ticker_response = requests.get(
            f"{self.base_url}/api/v1/market/stats?symbol={kucoin_symbol}"
        )
        ticker_data = ticker_response.json()["data"]

        # Get order book
        book_response = requests.get(
            f"{self.base_url}/api/v1/market/orderbook/level1?symbol={kucoin_symbol}"
        )
        book_data = book_response.json()["data"]

        return MarketData(
            symbol=symbol,
            price=float(ticker_data["last"]),
            bid=float(book_data["bestBid"]),
            ask=float(book_data["bestAsk"]),
            volume=float(ticker_data["vol"]),
            timestamp=time.time(),
            exchange="kucoin",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("KuCoin order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("KuCoin balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("KuCoin order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("KuCoin order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return True  # Available globally

    def _convert_symbol(self, symbol: str) -> str:
        """Convert standard symbol to KuCoin format"""
        # BTC-USD -> BTC-USDT
        return symbol.replace("-USD", "-USDT")


# Register all exchanges with the factory
from pt_exchange_abstraction import ExchangeFactory

ExchangeFactory.register_exchange(ExchangeType.ROBINHOOD, RobinhoodExchange)
ExchangeFactory.register_exchange(ExchangeType.KRAKEN, KrakenExchange)
ExchangeFactory.register_exchange(ExchangeType.BINANCE, BinanceExchange)
ExchangeFactory.register_exchange(ExchangeType.COINBASE, CoinbaseExchange)
ExchangeFactory.register_exchange(ExchangeType.KUCOIN, KuCoinExchange)


class HuobiExchange(AbstractExchange):
    """Huobi Global API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.huobi.pro"

    def get_exchange_name(self) -> str:
        return "huobi"

    def get_current_price(self, symbol: str) -> float:
        huobi_symbol = self._convert_symbol(symbol)
        response = requests.get(
            f"{self.base_url}/market/detail/merged?symbol={huobi_symbol}"
        )
        data = response.json()

        if data["status"] != "ok":
            raise RuntimeError(
                f"Huobi API error: {data.get('err-msg', 'Unknown error')}"
            )

        return float(data["tick"]["ask"][0])

    def get_market_data(self, symbol: str) -> MarketData:
        huobi_symbol = self._convert_symbol(symbol)
        response = requests.get(
            f"{self.base_url}/market/detail/merged?symbol={huobi_symbol}"
        )
        data = response.json()["tick"]

        return MarketData(
            symbol=symbol,
            price=float(data["close"]),
            bid=float(data["bid"][0]),
            ask=float(data["ask"][0]),
            volume=float(data["vol"]),
            timestamp=time.time(),
            exchange="huobi",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Huobi order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Huobi balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Huobi order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Huobi order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return region.upper() in ["EU", "UK", "ASIA", "GLOBAL"]

    def _convert_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Huobi format"""
        return symbol.replace("-", "").lower()


class GateExchange(AbstractExchange):
    """Gate.io API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.gateio.ws/api/v4"

    def get_exchange_name(self) -> str:
        return "gate"

    def get_current_price(self, symbol: str) -> float:
        gate_symbol = self._convert_symbol(symbol)
        response = requests.get(
            f"{self.base_url}/spot/tickers?currency_pair={gate_symbol}"
        )
        data = response.json()

        if not data or len(data) == 0:
            raise RuntimeError("Gate.io API error: No data returned")

        return float(data[0]["lowest_ask"])

    def get_market_data(self, symbol: str) -> MarketData:
        gate_symbol = self._convert_symbol(symbol)
        response = requests.get(
            f"{self.base_url}/spot/tickers?currency_pair={gate_symbol}"
        )
        data = response.json()[0]

        return MarketData(
            symbol=symbol,
            price=float(data["last"]),
            bid=float(data["highest_bid"]),
            ask=float(data["lowest_ask"]),
            volume=float(data["base_volume"]),
            timestamp=time.time(),
            exchange="gate",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Gate.io order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Gate.io balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Gate.io order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Gate.io order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return True  # Available globally

    def _convert_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Gate.io format"""
        return symbol.replace("-", "_")


class BitgetExchange(AbstractExchange):
    """Bitget API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.bitget.com"
        self.passphrase = kwargs.get("passphrase", "")

    def get_exchange_name(self) -> str:
        return "bitget"

    def get_current_price(self, symbol: str) -> float:
        bitget_symbol = self._convert_symbol(symbol)
        response = requests.get(
            f"{self.base_url}/api/spot/v1/market/ticker?symbol={bitget_symbol}"
        )
        data = response.json()

        if data["code"] != "00000":
            raise RuntimeError(f"Bitget API error: {data['msg']}")

        return float(data["data"]["askPr"])

    def get_market_data(self, symbol: str) -> MarketData:
        bitget_symbol = self._convert_symbol(symbol)
        response = requests.get(
            f"{self.base_url}/api/spot/v1/market/ticker?symbol={bitget_symbol}"
        )
        data = response.json()["data"]

        return MarketData(
            symbol=symbol,
            price=float(data["close"]),
            bid=float(data["bidPr"]),
            ask=float(data["askPr"]),
            volume=float(data["baseVol"]),
            timestamp=time.time(),
            exchange="bitget",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Bitget order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Bitget balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Bitget order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Bitget order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return True  # Available globally

    def _convert_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Bitget format"""
        return symbol.replace("-", "") + "_SPBL"


class MexcExchange(AbstractExchange):
    """MEXC API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.mexc.com"

    def get_exchange_name(self) -> str:
        return "mexc"

    def get_current_price(self, symbol: str) -> float:
        mexc_symbol = self._convert_symbol(symbol)
        response = requests.get(
            f"{self.base_url}/api/v3/ticker/price?symbol={mexc_symbol}"
        )
        data = response.json()

        if "code" in data:
            raise RuntimeError(f"MEXC API error: {data['msg']}")

        return float(data["price"])

    def get_market_data(self, symbol: str) -> MarketData:
        mexc_symbol = self._convert_symbol(symbol)
        ticker_response = requests.get(
            f"{self.base_url}/api/v3/ticker/24hr?symbol={mexc_symbol}"
        )
        ticker_data = ticker_response.json()

        book_response = requests.get(
            f"{self.base_url}/api/v3/ticker/bookTicker?symbol={mexc_symbol}"
        )
        book_data = book_response.json()

        return MarketData(
            symbol=symbol,
            price=float(ticker_data["lastPrice"]),
            bid=float(book_data["bidPrice"]),
            ask=float(book_data["askPrice"]),
            volume=float(ticker_data["volume"]),
            timestamp=time.time(),
            exchange="mexc",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("MEXC order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("MEXC balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("MEXC order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("MEXC order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return True  # Available globally

    def _convert_symbol(self, symbol: str) -> str:
        """Convert standard symbol to MEXC format"""
        return symbol.replace("-", "")


class BitfinexExchange(AbstractExchange):
    """Bitfinex API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api-pub.bitfinex.com/v2"

    def get_exchange_name(self) -> str:
        return "bitfinex"

    def get_current_price(self, symbol: str) -> float:
        bitfinex_symbol = self._convert_symbol(symbol)
        response = requests.get(f"{self.base_url}/ticker/t{bitfinex_symbol}")
        data = response.json()

        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(f"Bitfinex API error: {data['error']}")

        return float(data[2])  # Ask price

    def get_market_data(self, symbol: str) -> MarketData:
        bitfinex_symbol = self._convert_symbol(symbol)
        response = requests.get(f"{self.base_url}/ticker/t{bitfinex_symbol}")
        data = response.json()

        return MarketData(
            symbol=symbol,
            price=float(data[6]),  # Last price
            bid=float(data[0]),  # Bid
            ask=float(data[2]),  # Ask
            volume=float(data[7]),  # Volume
            timestamp=time.time(),
            exchange="bitfinex",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Bitfinex order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Bitfinex balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Bitfinex order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Bitfinex order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return region.upper() not in ["US", "USA"]  # Not available in US

    def _convert_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Bitfinex format"""
        return symbol.replace("-", "")


class OneInchExchange(AbstractExchange):
    """1inch DEX Aggregator API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.1inch.exchange/v4.0/1"  # Ethereum mainnet
        self.chain_id = kwargs.get("chain_id", 1)

    def get_exchange_name(self) -> str:
        return "oneinch"

    def get_current_price(self, symbol: str) -> float:
        # 1inch doesn't have traditional tickers, uses swap quotes
        token_address = self._get_token_address(symbol)
        response = requests.get(
            f"{self.base_url}/quote?fromTokenAddress={token_address}&toTokenAddress=0xA0b86a33E6bF6BC15Ac361e8C37f3E3B7AC3E80f&amount=1000000000000000000"
        )
        data = response.json()

        if "error" in data:
            raise RuntimeError(f"1inch API error: {data['description']}")

        return float(data["toTokenAmount"]) / 10**18

    def get_market_data(self, symbol: str) -> MarketData:
        # For DEX, market data is derived from swap quotes
        price = self.get_current_price(symbol)

        return MarketData(
            symbol=symbol,
            price=price,
            bid=price * 0.995,  # Approximate 0.5% spread
            ask=price * 1.005,
            volume=0.0,  # Volume data not readily available
            timestamp=time.time(),
            exchange="oneinch",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("1inch swap execution to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("1inch balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("1inch transaction status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        return False  # DEX transactions cannot be cancelled once submitted

    def is_available_in_region(self, region: str) -> bool:
        return True  # DeFi available globally

    def _get_token_address(self, symbol: str) -> str:
        """Get token contract address for symbol"""
        token_map = {
            "BTC-USD": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # WBTC
            "ETH-USD": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            "USDC-USD": "0xA0b86a33E6bF6BC15Ac361e8C37f3E3B7AC3E80f",  # USDC
        }
        return token_map.get(symbol, "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")


class UniswapExchange(AbstractExchange):
    """Uniswap V3 DEX implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3"
        self.infura_url = kwargs.get("infura_url", "")

    def get_exchange_name(self) -> str:
        return "uniswap"

    def get_current_price(self, symbol: str) -> float:
        # Query Uniswap subgraph for pool data
        pool_id = self._get_pool_id(symbol)

        query = f"""
        {{
          pool(id: "{pool_id}") {{
            token0Price
            token1Price
            volumeUSD
          }}
        }}
        """

        response = requests.post(self.base_url, json={"query": query})
        data = response.json()

        if "errors" in data:
            raise RuntimeError(f"Uniswap API error: {data['errors']}")

        return float(data["data"]["pool"]["token0Price"])

    def get_market_data(self, symbol: str) -> MarketData:
        price = self.get_current_price(symbol)

        return MarketData(
            symbol=symbol,
            price=price,
            bid=price * 0.997,  # Approximate 0.3% spread
            ask=price * 1.003,
            volume=0.0,  # Would need additional query
            timestamp=time.time(),
            exchange="uniswap",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Uniswap swap execution to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Uniswap balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Uniswap transaction status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        return False  # DEX transactions cannot be cancelled

    def is_available_in_region(self, region: str) -> bool:
        return True  # DeFi available globally

    def _get_pool_id(self, symbol: str) -> str:
        """Get Uniswap V3 pool ID for trading pair"""
        pool_map = {
            "BTC-USD": "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35",  # WBTC/USDC
            "ETH-USD": "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8",  # ETH/USDC
        }
        return pool_map.get(symbol, "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8")


# Register new exchanges
ExchangeFactory.register_exchange(ExchangeType.HUOBI, HuobiExchange)
ExchangeFactory.register_exchange(ExchangeType.GATE, GateExchange)
ExchangeFactory.register_exchange(ExchangeType.BITGET, BitgetExchange)
ExchangeFactory.register_exchange(ExchangeType.MEXC, MexcExchange)
ExchangeFactory.register_exchange(ExchangeType.BITFINEX, BitfinexExchange)
ExchangeFactory.register_exchange(ExchangeType.ONEINCH, OneInchExchange)
ExchangeFactory.register_exchange(ExchangeType.UNISWAP, UniswapExchange)


class CryptoComExchange(AbstractExchange):
    """Crypto.com Exchange API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.crypto.com/v2"

    def get_exchange_name(self) -> str:
        return "crypto_com"

    def get_current_price(self, symbol: str) -> float:
        cdc_symbol = self._convert_symbol(symbol)
        response = requests.get(
            f"{self.base_url}/public/get-ticker?instrument_name={cdc_symbol}"
        )
        data = response.json()

        if data["code"] != 0:
            raise RuntimeError(f"Crypto.com API error: {data['message']}")

        return float(data["result"]["data"]["a"])  # Ask price

    def get_market_data(self, symbol: str) -> MarketData:
        cdc_symbol = self._convert_symbol(symbol)
        response = requests.get(
            f"{self.base_url}/public/get-ticker?instrument_name={cdc_symbol}"
        )
        data = response.json()["result"]["data"]

        return MarketData(
            symbol=symbol,
            price=float(data["a"]),
            bid=float(data["b"]),
            ask=float(data["a"]),
            volume=float(data["v"]),
            timestamp=time.time(),
            exchange="crypto_com",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Crypto.com order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Crypto.com balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Crypto.com order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Crypto.com order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return region.upper() not in ["US"]  # Limited US access

    def _convert_symbol(self, symbol: str) -> str:
        return symbol.replace("-", "_")


class EtoroExchange(AbstractExchange):
    """eToro Social Trading API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.etoropartners.com/v2"
        self.username = kwargs.get("username", "")
        self.password = kwargs.get("password", "")

    def get_exchange_name(self) -> str:
        return "etoro"

    def get_current_price(self, symbol: str) -> float:
        etoro_symbol = self._convert_symbol(symbol)
        response = requests.get(f"{self.base_url}/instruments/{etoro_symbol}")
        data = response.json()

        return float(data["LastRates"]["Sell"])

    def get_market_data(self, symbol: str) -> MarketData:
        etoro_symbol = self._convert_symbol(symbol)
        response = requests.get(f"{self.base_url}/instruments/{etoro_symbol}")
        data = response.json()

        return MarketData(
            symbol=symbol,
            price=float(data["LastRates"]["Sell"]),
            bid=float(data["LastRates"]["Buy"]),
            ask=float(data["LastRates"]["Sell"]),
            volume=0.0,  # Volume not readily available
            timestamp=time.time(),
            exchange="etoro",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("eToro order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("eToro balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("eToro order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("eToro order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return True  # Available globally

    def _convert_symbol(self, symbol: str) -> str:
        symbol_map = {"BTC-USD": "BTC", "ETH-USD": "ETH", "ADA-USD": "ADA"}
        return symbol_map.get(symbol, symbol.split("-")[0])


class UpbitExchange(AbstractExchange):
    """Upbit Korean Exchange API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.upbit.com/v1"

    def get_exchange_name(self) -> str:
        return "upbit"

    def get_current_price(self, symbol: str) -> float:
        upbit_symbol = self._convert_symbol(symbol)
        response = requests.get(f"{self.base_url}/ticker?markets={upbit_symbol}")
        data = response.json()

        if "error" in data:
            raise RuntimeError(f"Upbit API error: {data['error']}")

        return float(data[0]["trade_price"])

    def get_market_data(self, symbol: str) -> MarketData:
        upbit_symbol = self._convert_symbol(symbol)
        response = requests.get(f"{self.base_url}/ticker?markets={upbit_symbol}")
        data = response.json()[0]

        return MarketData(
            symbol=symbol,
            price=float(data["trade_price"]),
            bid=float(data["trade_price"]),  # Upbit doesn't provide separate bid/ask
            ask=float(data["trade_price"]),
            volume=float(data["acc_trade_volume_24h"]),
            timestamp=time.time(),
            exchange="upbit",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Upbit order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Upbit balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Upbit order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Upbit order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return region.upper() in ["KR", "KOREA", "SOUTH_KOREA"]

    def _convert_symbol(self, symbol: str) -> str:
        # BTC-USD -> KRW-BTC (KRW base for Korean market)
        coin = symbol.split("-")[0]
        return f"KRW-{coin}"


class DydxExchange(AbstractExchange):
    """dYdX Perpetual DEX implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.dydx.exchange"
        self.stark_private_key = kwargs.get("stark_private_key", "")

    def get_exchange_name(self) -> str:
        return "dydx"

    def get_current_price(self, symbol: str) -> float:
        dydx_symbol = self._convert_symbol(symbol)
        response = requests.get(f"{self.base_url}/v3/markets/{dydx_symbol}")
        data = response.json()

        return float(data["market"]["oraclePrice"])

    def get_market_data(self, symbol: str) -> MarketData:
        dydx_symbol = self._convert_symbol(symbol)
        response = requests.get(f"{self.base_url}/v3/markets/{dydx_symbol}")
        data = response.json()["market"]

        return MarketData(
            symbol=symbol,
            price=float(data["oraclePrice"]),
            bid=float(data["oraclePrice"]) * 0.999,  # Approximate
            ask=float(data["oraclePrice"]) * 1.001,
            volume=float(data["volume24H"]),
            timestamp=time.time(),
            exchange="dydx",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("dYdX order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("dYdX balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("dYdX order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("dYdX order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return region.upper() not in ["US"]  # US restrictions

    def _convert_symbol(self, symbol: str) -> str:
        symbol_map = {
            "BTC-USD": "BTC-USD",
            "ETH-USD": "ETH-USD",
            "LINK-USD": "LINK-USD",
        }
        return symbol_map.get(symbol, symbol)


class CurveExchange(AbstractExchange):
    """Curve Finance DEX implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.curve.fi/api"
        self.web3_provider = kwargs.get("web3_provider", "")

    def get_exchange_name(self) -> str:
        return "curve"

    def get_current_price(self, symbol: str) -> float:
        # Curve specializes in stablecoin pairs - prices are near 1.0
        if "USD" in symbol:
            return 1.0  # Stablecoin to stablecoin approximation

        response = requests.get(f"{self.base_url}/getPools")
        data = response.json()

        # Find relevant pool for symbol
        for pool in data["data"]["poolData"]:
            if symbol.split("-")[0].upper() in pool["name"].upper():
                return float(pool.get("virtualPrice", 1.0))

        return 1.0

    def get_market_data(self, symbol: str) -> MarketData:
        price = self.get_current_price(symbol)

        return MarketData(
            symbol=symbol,
            price=price,
            bid=price * 0.9995,  # Very tight spreads for stablecoins
            ask=price * 1.0005,
            volume=0.0,  # Volume requires more complex calculation
            timestamp=time.time(),
            exchange="curve",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Curve swap execution to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Curve balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Curve transaction status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        return False  # DEX transactions cannot be cancelled

    def is_available_in_region(self, region: str) -> bool:
        return True  # DeFi available globally

    def _convert_symbol(self, symbol: str) -> str:
        return symbol.replace("-", "/")


class PhemexExchange(AbstractExchange):
    """Phemex Exchange API implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.phemex.com"

    def get_exchange_name(self) -> str:
        return "phemex"

    def get_current_price(self, symbol: str) -> float:
        phemex_symbol = self._convert_symbol(symbol)
        response = requests.get(
            f"{self.base_url}/md/ticker/24hr?symbol={phemex_symbol}"
        )
        data = response.json()

        if "code" in data and data["code"] != 0:
            raise RuntimeError(f"Phemex API error: {data['msg']}")

        return float(data["result"]["askPx"]) / 10000  # Phemex uses scaled prices

    def get_market_data(self, symbol: str) -> MarketData:
        phemex_symbol = self._convert_symbol(symbol)
        response = requests.get(
            f"{self.base_url}/md/ticker/24hr?symbol={phemex_symbol}"
        )
        data = response.json()["result"]

        return MarketData(
            symbol=symbol,
            price=float(data["lastPx"]) / 10000,
            bid=float(data["bidPx"]) / 10000,
            ask=float(data["askPx"]) / 10000,
            volume=float(data["volume"]),
            timestamp=time.time(),
            exchange="phemex",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Phemex order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Phemex balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Phemex order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Phemex order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return True  # Available globally

    def _convert_symbol(self, symbol: str) -> str:
        return symbol.replace("-", "")


# Register all new exchanges
ExchangeFactory.register_exchange(ExchangeType.CRYPTO_COM, CryptoComExchange)
ExchangeFactory.register_exchange(ExchangeType.ETORO, EtoroExchange)
ExchangeFactory.register_exchange(ExchangeType.UPBIT, UpbitExchange)
ExchangeFactory.register_exchange(ExchangeType.DYDX, DydxExchange)
ExchangeFactory.register_exchange(ExchangeType.CURVE, CurveExchange)
ExchangeFactory.register_exchange(ExchangeType.PHEMEX, PhemexExchange)


class BitsoExchange(AbstractExchange):
    """Bitso Exchange API implementation - Latin America's leading exchange"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://api.bitso.com/v3"
        self.passphrase = kwargs.get("passphrase", "")

    def get_exchange_name(self) -> str:
        return "bitso"

    def get_current_price(self, symbol: str) -> float:
        market_data = self.get_market_data(symbol)
        return market_data.price

    def get_market_data(self, symbol: str) -> MarketData:
        bitso_symbol = self._convert_symbol(symbol)
        response = requests.get(f"{self.base_url}/ticker?book={bitso_symbol}")
        data = response.json()["payload"]

        return MarketData(
            symbol=symbol,
            price=float(data["last"]),
            bid=float(data["bid"]),
            ask=float(data["ask"]),
            volume=float(data["volume"]),
            timestamp=time.time(),
            exchange="bitso",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Bitso order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Bitso balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Bitso order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Bitso order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        return region.upper() in ["MX", "AR", "BR", "CO"]  # Latin America

    def _convert_symbol(self, symbol: str) -> str:
        return symbol.replace("-", "_").lower()


class AaveExchange(AbstractExchange):
    """Aave Protocol DeFi Lending implementation"""

    def __init__(self, wallet_address: str, private_key: str, **kwargs):
        super().__init__(wallet_address, private_key, **kwargs)
        self.base_url = "https://api.aave.com/v1"
        self.web3_provider = kwargs.get("web3_provider")

    def get_exchange_name(self) -> str:
        return "aave"

    def get_current_price(self, symbol: str) -> float:
        market_data = self.get_market_data(symbol)
        return market_data.price

    def get_market_data(self, symbol: str) -> MarketData:
        # Get lending/borrowing rates for asset
        response = requests.get(f"{self.base_url}/reserves/{symbol}")
        data = response.json()

        return MarketData(
            symbol=symbol,
            price=float(data["priceInEth"]),  # Price in ETH
            bid=float(data["liquidityRate"]),  # Lending rate
            ask=float(data["variableBorrowRate"]),  # Borrowing rate
            volume=float(data["totalLiquidity"]),
            timestamp=time.time(),
            exchange="aave",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        # In Aave, "orders" are deposit/borrow operations
        if side.lower() == "buy":
            # Deposit (lend) operation
            return self._deposit(symbol, amount)
        else:
            # Borrow operation
            return self._borrow(symbol, amount)

    def _deposit(self, symbol: str, amount: float) -> OrderResult:
        raise NotImplementedError("Aave deposit to be implemented")

    def _borrow(self, symbol: str, amount: float) -> OrderResult:
        raise NotImplementedError("Aave borrow to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Aave balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Aave transaction status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        return False  # DeFi transactions cannot be cancelled once submitted

    def is_available_in_region(self, region: str) -> bool:
        return True  # Available globally via DeFi


class YearnFinanceExchange(AbstractExchange):
    """Yearn Finance Yield Aggregator implementation"""

    def __init__(self, wallet_address: str, private_key: str, **kwargs):
        super().__init__(wallet_address, private_key, **kwargs)
        self.base_url = "https://api.yearn.finance/v1"

    def get_exchange_name(self) -> str:
        return "yearn_finance"

    def get_current_price(self, symbol: str) -> float:
        market_data = self.get_market_data(symbol)
        return market_data.price

    def get_market_data(self, symbol: str) -> MarketData:
        # Get vault information
        response = requests.get(f"{self.base_url}/vaults/{symbol}")
        data = response.json()

        return MarketData(
            symbol=symbol,
            price=float(data["token"]["price"]),
            bid=0.0,  # Not applicable for yield vaults
            ask=0.0,  # Not applicable for yield vaults
            volume=float(data["tvl"]["value"]),  # TVL as volume
            timestamp=time.time(),
            exchange="yearn_finance",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        if side.lower() == "buy":
            return self._deposit_to_vault(symbol, amount)
        else:
            return self._withdraw_from_vault(symbol, amount)

    def _deposit_to_vault(self, vault_address: str, amount: float) -> OrderResult:
        raise NotImplementedError("Yearn vault deposit to be implemented")

    def _withdraw_from_vault(self, vault_address: str, amount: float) -> OrderResult:
        raise NotImplementedError("Yearn vault withdrawal to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Yearn balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Yearn transaction status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        return False  # DeFi transactions cannot be cancelled

    def is_available_in_region(self, region: str) -> bool:
        return True  # Available globally via DeFi


class DeribitExchange(AbstractExchange):
    """Deribit Options & Futures Exchange implementation"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.base_url = "https://www.deribit.com/api/v2"
        self.testnet = kwargs.get("testnet", False)
        if self.testnet:
            self.base_url = "https://test.deribit.com/api/v2"

    def get_exchange_name(self) -> str:
        return "deribit"

    def get_current_price(self, symbol: str) -> float:
        market_data = self.get_market_data(symbol)
        return market_data.price

    def get_market_data(self, symbol: str) -> MarketData:
        response = requests.get(
            f"{self.base_url}/public/get_book_summary_by_instrument?instrument_name={symbol}"
        )
        data = response.json()["result"][0]

        return MarketData(
            symbol=symbol,
            price=float(data["last_price"]),
            bid=float(data["bid_price"]),
            ask=float(data["ask_price"]),
            volume=float(data["volume"]),
            timestamp=time.time(),
            exchange="deribit",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        raise NotImplementedError("Deribit order placement to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Deribit balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Deribit order status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Deribit order cancellation to be implemented")

    def is_available_in_region(self, region: str) -> bool:
        # Restricted in some regions
        restricted_regions = ["US", "CA", "JP"]
        return region.upper() not in restricted_regions


class LidoFinanceExchange(AbstractExchange):
    """Lido Finance Liquid Staking implementation"""

    def __init__(self, wallet_address: str, private_key: str, **kwargs):
        super().__init__(wallet_address, private_key, **kwargs)
        self.base_url = "https://api.lido.fi/v1"

    def get_exchange_name(self) -> str:
        return "lido_finance"

    def get_current_price(self, symbol: str) -> float:
        market_data = self.get_market_data(symbol)
        return market_data.price

    def get_market_data(self, symbol: str) -> MarketData:
        # Get stETH information
        response = requests.get(f"{self.base_url}/protocol/steth/apr")
        apr_data = response.json()

        # Get stETH price
        price_response = requests.get(f"{self.base_url}/protocol/steth/price")
        price_data = price_response.json()

        return MarketData(
            symbol=symbol,
            price=float(price_data["steth_price"]),
            bid=float(apr_data["apr"]),  # APR as bid
            ask=0.0,  # No borrowing rate
            volume=float(apr_data["total_staked"]),
            timestamp=time.time(),
            exchange="lido_finance",
        )

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        if side.lower() == "buy":
            return self._stake_eth(amount)
        else:
            return self._unstake_eth(amount)

    def _stake_eth(self, amount: float) -> OrderResult:
        raise NotImplementedError("Lido ETH staking to be implemented")

    def _unstake_eth(self, amount: float) -> OrderResult:
        raise NotImplementedError("Lido ETH unstaking to be implemented")

    def get_balance(self) -> Dict[str, float]:
        raise NotImplementedError("Lido balance retrieval to be implemented")

    def get_order_status(self, order_id: str) -> OrderResult:
        raise NotImplementedError("Lido transaction status to be implemented")

    def cancel_order(self, order_id: str) -> bool:
        return False  # Staking transactions cannot be cancelled

    def is_available_in_region(self, region: str) -> bool:
        return True  # Available globally via DeFi


# Register all additional exchanges
ExchangeFactory.register_exchange(ExchangeType.BITSO, BitsoExchange)
ExchangeFactory.register_exchange(ExchangeType.AAVE, AaveExchange)
ExchangeFactory.register_exchange(ExchangeType.YEARN_FINANCE, YearnFinanceExchange)
ExchangeFactory.register_exchange(ExchangeType.DERIBIT, DeribitExchange)
ExchangeFactory.register_exchange(ExchangeType.LIDO_FINANCE, LidoFinanceExchange)
