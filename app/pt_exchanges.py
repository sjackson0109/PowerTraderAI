"""
Specific Exchange Implementations
All major cryptocurrency exchanges with unified interface
"""

import base64
import hashlib
import hmac
import json
import time
from decimal import ROUND_DOWN, Decimal, InvalidOperation
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


_BINANCE_PROD_REST = "https://api.binance.com"
_BINANCE_TESTNET_REST = "https://testnet.binance.vision"
_BINANCE_PROD_WS = "wss://stream.binance.com:9443/ws"
_BINANCE_TESTNET_WS = "wss://stream.testnet.binance.vision/ws"

# Limit/stop order types per Binance spot docs
_BINANCE_SPOT_ORDER_TYPES = {
    "MARKET",
    "LIMIT",
    "STOP_LOSS",
    "STOP_LOSS_LIMIT",
    "TAKE_PROFIT",
    "TAKE_PROFIT_LIMIT",
    "LIMIT_MAKER",
}
_BINANCE_LIMIT_TYPES = {
    "LIMIT",
    "STOP_LOSS_LIMIT",
    "TAKE_PROFIT_LIMIT",
    "LIMIT_MAKER",
}
_BINANCE_STOP_TYPES = {
    "STOP_LOSS",
    "STOP_LOSS_LIMIT",
    "TAKE_PROFIT",
    "TAKE_PROFIT_LIMIT",
}


class BinanceRateLimitError(RuntimeError):
    """Raised on HTTP 429/418 from Binance. Carries retry-after (seconds)."""

    def __init__(self, status_code: int, retry_after: float, message: str = ""):
        super().__init__(
            f"Binance rate limit ({status_code}): retry after {retry_after}s. {message}"
        )
        self.status_code = status_code
        self.retry_after = retry_after


class BinanceTimestampError(RuntimeError):
    """Raised on -1021 (timestamp outside recvWindow) after auto-resync retry."""


class BinanceExchange(AbstractExchange):
    """Binance Spot API implementation.

    Covers signed order placement (all spot types), OCO, balance, order
    status/cancel, exchange-filter enforcement, server-time sync, rate-limit
    awareness, and user-data-stream listenKey lifecycle. Production + testnet
    base URLs are selected via the ``testnet`` constructor flag so the
    multi-broker selector (#96) can flip the toggle per user preference.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = False,
        recv_window: int = 5000,
        **kwargs,
    ):
        super().__init__(api_key, api_secret, **kwargs)
        self.testnet = bool(testnet)
        self.base_url = _BINANCE_TESTNET_REST if self.testnet else _BINANCE_PROD_REST
        self.ws_base = _BINANCE_TESTNET_WS if self.testnet else _BINANCE_PROD_WS
        # Per Binance docs: default 5000ms, max 60000ms
        self.recv_window = max(1, min(int(recv_window), 60000))
        # Per-symbol filter cache: {binance_symbol: {"stepSize": Decimal,
        # "tickSize": Decimal, "minQty": Decimal, "minNotional": Decimal}}.
        # Populated lazily by _get_symbol_filters() to avoid per-order REST.
        self._symbol_filters: Dict[str, Dict[str, Decimal]] = {}
        # Server-time offset in ms: server_ms - local_ms. Refreshed lazily and
        # again on -1021 retry. Keeps timestamps inside recvWindow without a
        # round-trip on every order.
        self._time_offset_ms: int = 0
        self._time_synced: bool = False
        # Last-seen rate-limit headers, keyed by header name (e.g.
        # "X-MBX-USED-WEIGHT-1M"). Exposed for monitoring; not consulted to
        # decide throttling — Binance's 429 + Retry-After is authoritative.
        self.last_rate_limit_headers: Dict[str, str] = {}

    def get_exchange_name(self) -> str:
        return "binance"

    def get_masked_api_key(self) -> str:
        """Return ``****<last4>`` for display by the broker selector UI."""
        if not self.api_key:
            return "Not configured"
        suffix = self.api_key[-4:] if len(self.api_key) >= 4 else self.api_key
        return f"****{suffix}"

    def test_connection(self) -> bool:
        """Probe credentials by hitting the account endpoint.

        Returns True on success, False on any auth/credential/network failure.
        Used by the broker selector (#96) for the per-row "Test connection"
        button without raising into the GUI thread.
        """
        if not self.api_key or not self.api_secret:
            return False
        try:
            self._signed_request("GET", "/api/v3/account")
            return True
        except Exception:
            return False

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

    # ------------------------------------------------------------------
    # Server-time sync
    # ------------------------------------------------------------------

    def sync_time(self) -> int:
        """Fetch /api/v3/time and cache the local-vs-server offset (ms).

        Called lazily before the first signed request and again on a -1021
        ("timestamp for this request was 1000ms ahead of the server's time")
        retry. Returns the offset for tests/diagnostics.
        """
        response = requests.get(f"{self.base_url}/api/v3/time", timeout=10)
        data = response.json()
        if "serverTime" not in data:
            raise RuntimeError(f"Binance /api/v3/time unexpected response: {data}")
        self._time_offset_ms = int(data["serverTime"]) - int(time.time() * 1000)
        self._time_synced = True
        return self._time_offset_ms

    def _now_ms(self) -> int:
        """Local wall clock corrected by the cached server-time offset."""
        return int(time.time() * 1000) + self._time_offset_ms

    # ------------------------------------------------------------------
    # Authenticated helpers
    # ------------------------------------------------------------------

    def _sign(self, params: str) -> str:
        """Generate HMAC-SHA256 signature for Binance signed endpoints."""
        return hmac.new(
            self.api_secret.encode("utf-8"),
            params.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _signed_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        _retried_on_timestamp: bool = False,
    ) -> Dict:
        """
        Make a signed request to a Binance private endpoint.

        Injects ``timestamp`` (corrected by the cached server-time offset) and
        ``recvWindow``, signs the canonical query with HMAC-SHA256, and posts
        with the ``X-MBX-APIKEY`` header. On HTTP 429/418 raises
        :class:`BinanceRateLimitError` honouring ``Retry-After``. On Binance
        error -1021 (timestamp drift), resyncs and retries exactly once.

        Raises:
            BinanceRateLimitError: on HTTP 429 (weight) or 418 (IP ban).
            BinanceTimestampError: -1021 still failing after a resync retry.
            RuntimeError: any other Binance error (negative ``code`` field).
            requests.RequestException: network failure.
        """
        if not self._time_synced:
            # Best-effort; if /api/v3/time fails the unsynced timestamp will
            # still work for users whose clocks are within recvWindow.
            try:
                self.sync_time()
            except Exception:
                pass

        params = params or {}
        params.setdefault("recvWindow", self.recv_window)
        params["timestamp"] = self._now_ms()
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = self._sign(query)
        query += f"&signature={signature}"

        url = f"{self.base_url}{path}?{query}"
        headers = {"X-MBX-APIKEY": self.api_key}

        send = {
            "GET": requests.get,
            "POST": requests.post,
            "DELETE": requests.delete,
            "PUT": requests.put,
        }.get(method.upper())
        if send is None:
            raise ValueError(f"Unsupported HTTP method: {method}")

        response = send(url, headers=headers, timeout=10)

        # Capture rate-limit headers regardless of status. Header names are
        # case-insensitive and follow X-MBX-USED-WEIGHT-(intervalNum)(letter)
        # / X-MBX-ORDER-COUNT-* per Binance spec.
        try:
            self.last_rate_limit_headers = {
                k: v
                for k, v in response.headers.items()
                if k.upper().startswith(("X-MBX-USED-WEIGHT", "X-MBX-ORDER-COUNT"))
            }
        except Exception:
            pass

        status = response.status_code
        if status in (429, 418):
            retry_after = float(response.headers.get("Retry-After", "0") or 0)
            msg = ""
            try:
                msg = response.json().get("msg", "")
            except Exception:
                pass
            raise BinanceRateLimitError(status, retry_after, msg)

        data = response.json()
        if isinstance(data, dict) and "code" in data and data["code"] < 0:
            # -1021: timestamp outside recvWindow. Resync and retry once.
            if data["code"] == -1021 and not _retried_on_timestamp:
                try:
                    self.sync_time()
                except Exception:
                    raise BinanceTimestampError(
                        f"Binance -1021 and /api/v3/time resync failed: "
                        f"{data.get('msg', '')}"
                    )
                return self._signed_request(
                    method,
                    path,
                    params={
                        k: v
                        for k, v in params.items()
                        if k not in ("timestamp", "signature")
                    },
                    _retried_on_timestamp=True,
                )
            if data["code"] == -1021:
                raise BinanceTimestampError(
                    f"Binance -1021 after resync retry: {data.get('msg', '')}"
                )
            raise RuntimeError(
                f"Binance API error {data['code']}: {data.get('msg', '')}"
            )
        return data

    def _public_request(
        self, method: str, path: str, headers: Optional[Dict] = None
    ) -> Dict:
        """Unsigned API-key request (e.g. POST /api/v3/userDataStream).

        These endpoints need ``X-MBX-APIKEY`` but no signature.
        """
        send = {
            "GET": requests.get,
            "POST": requests.post,
            "PUT": requests.put,
            "DELETE": requests.delete,
        }.get(method.upper())
        if send is None:
            raise ValueError(f"Unsupported HTTP method: {method}")
        merged = {"X-MBX-APIKEY": self.api_key}
        if headers:
            merged.update(headers)
        response = send(f"{self.base_url}{path}", headers=merged, timeout=10)
        data = response.json() if response.content else {}
        if isinstance(data, dict) and "code" in data and data["code"] < 0:
            raise RuntimeError(
                f"Binance API error {data['code']}: {data.get('msg', '')}"
            )
        return data

    # ------------------------------------------------------------------
    # Symbol filter handling (LOT_SIZE, PRICE_FILTER, MIN_NOTIONAL)
    # ------------------------------------------------------------------

    def _get_symbol_filters(self, binance_symbol: str) -> Dict[str, Decimal]:
        """
        Fetch and cache the trading filters for a symbol from
        /api/v3/exchangeInfo. Subsequent calls hit the in-memory cache so
        each order placement does not pay a REST round-trip.

        Returns dict with keys: stepSize, tickSize, minQty, minNotional.
        Missing filters are returned as Decimal("0") so callers can treat
        them as "no constraint".
        """
        if binance_symbol in self._symbol_filters:
            return self._symbol_filters[binance_symbol]

        url = f"{self.base_url}/api/v3/exchangeInfo?symbol={binance_symbol}"
        response = requests.get(url, timeout=10)
        info = response.json()
        if "symbols" not in info or not info["symbols"]:
            raise RuntimeError(
                f"Binance exchangeInfo returned no data for {binance_symbol}"
            )

        filters: Dict[str, Decimal] = {
            "stepSize": Decimal("0"),
            "tickSize": Decimal("0"),
            "minQty": Decimal("0"),
            "minNotional": Decimal("0"),
        }
        for f in info["symbols"][0].get("filters", []):
            try:
                if f["filterType"] == "LOT_SIZE":
                    filters["stepSize"] = Decimal(f["stepSize"])
                    filters["minQty"] = Decimal(f["minQty"])
                elif f["filterType"] == "PRICE_FILTER":
                    filters["tickSize"] = Decimal(f["tickSize"])
                elif f["filterType"] in ("MIN_NOTIONAL", "NOTIONAL"):
                    # Binance renamed MIN_NOTIONAL -> NOTIONAL in 2023;
                    # support both so older and newer pairs both work.
                    filters["minNotional"] = Decimal(
                        f.get("minNotional", f.get("notional", "0"))
                    )
            except (InvalidOperation, KeyError):
                # Unknown filter shape: skip rather than blowing up the order.
                continue

        self._symbol_filters[binance_symbol] = filters
        return filters

    @staticmethod
    def _round_to_step(value: Decimal, step: Decimal) -> Decimal:
        """
        Round ``value`` *down* to the nearest multiple of ``step``.

        Truncating (ROUND_DOWN) — never rounding up — keeps the submitted
        quantity at or below the user's intent. Rounding up could exceed
        available balance, overshoot a stop, or violate a per-trade cap.
        """
        if step == 0:
            return value
        quantised = (value / step).to_integral_value(rounding=ROUND_DOWN) * step
        # Normalise away trailing zeros so Binance accepts e.g. "0.001"
        # instead of "0.00100000" which can fail the PRICE_FILTER regex.
        return quantised.normalize()

    # ------------------------------------------------------------------
    # AbstractExchange implementation
    # ------------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        order_type: Optional[str] = None,
        stop_price: Optional[float] = None,
        time_in_force: Optional[str] = None,
        iceberg_qty: Optional[float] = None,
        quote_order_qty: Optional[float] = None,
        client_order_id: Optional[str] = None,
        trailing_delta: Optional[int] = None,
    ) -> OrderResult:
        """
        Place a spot order on Binance via POST /api/v3/order.

        Supports the full Binance spot type set: ``MARKET``, ``LIMIT``,
        ``STOP_LOSS``, ``STOP_LOSS_LIMIT``, ``TAKE_PROFIT``,
        ``TAKE_PROFIT_LIMIT``, ``LIMIT_MAKER``. ``order_type`` may be passed
        explicitly; if omitted, the caller stays backwards compatible —
        ``LIMIT`` when ``price`` is provided, else ``MARKET``.

        Args:
            symbol: Standard format e.g. 'BTC-USD' (converted to BTCUSDT)
            side: 'buy' or 'sell'
            amount: Quantity of base asset
            price: Limit price (required for LIMIT/*_LIMIT/LIMIT_MAKER)
            order_type: Override the auto-derived type
            stop_price: Trigger price (required for STOP_* / TAKE_PROFIT*)
            time_in_force: GTC/IOC/FOK (defaulted to GTC for limit types)
            iceberg_qty: Visible portion for iceberg orders (GTC only)
            quote_order_qty: Quote-asset spend (MARKET only; alt to amount)
            client_order_id: User-supplied order id (newClientOrderId)
            trailing_delta: BIPS for trailing stop (alternative to stop_price)

        Quantity is rounded *down* to the symbol's LOT_SIZE step and any
        price field is rounded *down* to the PRICE_FILTER tick. After
        rounding, the order is rejected locally with RuntimeError if
        quantity < minQty or quantity * price < minNotional, so the user
        sees a useful error instead of Binance's opaque -1013 / -1100.

        Returns:
            OrderResult. order_id uses 'SYMBOL:ID' format for later lookup.

        Raises:
            ValueError: on unsupported order_type or missing required fields
            RuntimeError: on missing credentials, filter violation, or API error
        """
        if not self.api_key or not self.api_secret:
            raise RuntimeError("Binance API credentials required for order placement")

        binance_symbol = self._convert_symbol(symbol)
        # Auto-derive: keeps the legacy (symbol, side, amount[, price]) signature
        # behaving exactly as it did before this change.
        if order_type is None:
            otype = "LIMIT" if price is not None else "MARKET"
        else:
            otype = order_type.upper()
        if otype not in _BINANCE_SPOT_ORDER_TYPES:
            raise ValueError(
                f"Unsupported Binance order type '{otype}'. "
                f"Expected one of: {sorted(_BINANCE_SPOT_ORDER_TYPES)}"
            )

        # Per-type required-field guards. Matches Binance trading-endpoints
        # spec so callers get a clean ValueError instead of -1102/-1106.
        if otype in _BINANCE_LIMIT_TYPES and price is None:
            raise ValueError(f"Binance {otype} requires price")
        if (
            otype in _BINANCE_STOP_TYPES
            and stop_price is None
            and trailing_delta is None
        ):
            raise ValueError(f"Binance {otype} requires stop_price or trailing_delta")
        if otype == "MARKET" and quote_order_qty is not None and amount:
            raise ValueError(
                "Binance MARKET accepts amount OR quote_order_qty, not both"
            )

        # Apply LOT_SIZE / PRICE_FILTER / MIN_NOTIONAL before signing.
        filters = self._get_symbol_filters(binance_symbol)
        qty_dec = self._round_to_step(Decimal(str(amount)), filters["stepSize"])
        price_dec: Optional[Decimal] = None
        if price is not None:
            price_dec = self._round_to_step(Decimal(str(price)), filters["tickSize"])
        stop_dec: Optional[Decimal] = None
        if stop_price is not None:
            stop_dec = self._round_to_step(
                Decimal(str(stop_price)), filters["tickSize"]
            )

        if filters["minQty"] > 0 and qty_dec < filters["minQty"] and amount:
            raise RuntimeError(
                f"Binance {binance_symbol} order quantity {qty_dec} below "
                f"minQty {filters['minQty']} after LOT_SIZE rounding"
            )
        if filters["minNotional"] > 0 and price_dec is not None and amount:
            notional = qty_dec * price_dec
            if notional < filters["minNotional"]:
                raise RuntimeError(
                    f"Binance {binance_symbol} notional {notional} below "
                    f"minNotional {filters['minNotional']}"
                )

        params: Dict = {
            "symbol": binance_symbol,
            "side": side.upper(),
            "type": otype,
        }
        if quote_order_qty is not None and otype == "MARKET":
            params["quoteOrderQty"] = format(Decimal(str(quote_order_qty)), "f")
        else:
            params["quantity"] = format(qty_dec, "f")

        if otype in _BINANCE_LIMIT_TYPES:
            params["price"] = format(price_dec, "f")
            params["timeInForce"] = (time_in_force or "GTC").upper()
        if otype in _BINANCE_STOP_TYPES and stop_dec is not None:
            params["stopPrice"] = format(stop_dec, "f")
        if trailing_delta is not None:
            params["trailingDelta"] = int(trailing_delta)
        if iceberg_qty is not None:
            params["icebergQty"] = format(Decimal(str(iceberg_qty)), "f")
        if client_order_id:
            params["newClientOrderId"] = client_order_id

        data = self._signed_request("POST", "/api/v3/order", params)

        # Prefix order_id with symbol so get_order_status/cancel_order can use it
        compound_id = f"{binance_symbol}:{data['orderId']}"

        return OrderResult(
            order_id=compound_id,
            symbol=symbol,
            side=side.lower(),
            amount=float(data.get("executedQty", amount)),
            price=float(data.get("price", price or 0)),
            status=data.get("status", "UNKNOWN").lower(),
            exchange="binance",
            timestamp=data.get("transactTime", time.time() * 1000) / 1000,
        )

    # ------------------------------------------------------------------
    # OCO (One-Cancels-the-Other) - POST /api/v3/orderList/oco
    # ------------------------------------------------------------------

    def place_oco_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        above_type: str,
        below_type: str,
        above_price: Optional[float] = None,
        above_stop_price: Optional[float] = None,
        above_time_in_force: Optional[str] = None,
        below_price: Optional[float] = None,
        below_stop_price: Optional[float] = None,
        below_time_in_force: Optional[str] = None,
        list_client_order_id: Optional[str] = None,
    ) -> Dict:
        """Place an OCO order list via the modern ``/api/v3/orderList/oco``.

        Each leg is described with ``aboveType`` / ``belowType`` + the leg's
        price/stopPrice/timeInForce — this is the new schema Binance moved to
        in 2024, replacing the legacy flat ``/api/v3/order/oco`` shape.

        Price restrictions are enforced server-side:
            * SELL: LIMIT_MAKER price > last > STOP_LOSS_LIMIT stopPrice
            * BUY:  LIMIT_MAKER price < last < STOP_LOSS_LIMIT stopPrice

        Returns:
            Raw Binance response dict (orderListId, contingencyType, orders, ...)
        """
        if not self.api_key or not self.api_secret:
            raise RuntimeError("Binance API credentials required for OCO placement")

        binance_symbol = self._convert_symbol(symbol)
        filters = self._get_symbol_filters(binance_symbol)
        qty_dec = self._round_to_step(Decimal(str(quantity)), filters["stepSize"])

        if filters["minQty"] > 0 and qty_dec < filters["minQty"]:
            raise RuntimeError(
                f"Binance OCO {binance_symbol} quantity {qty_dec} below "
                f"minQty {filters['minQty']}"
            )

        params: Dict = {
            "symbol": binance_symbol,
            "side": side.upper(),
            "quantity": format(qty_dec, "f"),
            "aboveType": above_type.upper(),
            "belowType": below_type.upper(),
        }
        if above_price is not None:
            params["abovePrice"] = format(
                self._round_to_step(Decimal(str(above_price)), filters["tickSize"]),
                "f",
            )
        if above_stop_price is not None:
            params["aboveStopPrice"] = format(
                self._round_to_step(
                    Decimal(str(above_stop_price)), filters["tickSize"]
                ),
                "f",
            )
        if above_time_in_force:
            params["aboveTimeInForce"] = above_time_in_force.upper()
        if below_price is not None:
            params["belowPrice"] = format(
                self._round_to_step(Decimal(str(below_price)), filters["tickSize"]),
                "f",
            )
        if below_stop_price is not None:
            params["belowStopPrice"] = format(
                self._round_to_step(
                    Decimal(str(below_stop_price)), filters["tickSize"]
                ),
                "f",
            )
        if below_time_in_force:
            params["belowTimeInForce"] = below_time_in_force.upper()
        if list_client_order_id:
            params["listClientOrderId"] = list_client_order_id

        return self._signed_request("POST", "/api/v3/orderList/oco", params)

    def cancel_order_list(
        self,
        symbol: str,
        order_list_id: Optional[int] = None,
        list_client_order_id: Optional[str] = None,
    ) -> Dict:
        """Cancel an entire OCO list via DELETE ``/api/v3/orderList``.

        Cancelling any single leg cancels the whole list per Binance spec, so
        callers usually want this rather than two individual cancels.
        """
        if not self.api_key or not self.api_secret:
            raise RuntimeError("Binance API credentials required for OCO cancel")
        if order_list_id is None and list_client_order_id is None:
            raise ValueError(
                "cancel_order_list requires order_list_id or list_client_order_id"
            )
        binance_symbol = self._convert_symbol(symbol)
        params: Dict = {"symbol": binance_symbol}
        if order_list_id is not None:
            params["orderListId"] = int(order_list_id)
        if list_client_order_id is not None:
            params["listClientOrderId"] = list_client_order_id
        return self._signed_request("DELETE", "/api/v3/orderList", params)

    # ------------------------------------------------------------------
    # User-data stream (listenKey lifecycle)
    # ------------------------------------------------------------------

    def create_listen_key(self) -> str:
        """POST /api/v3/userDataStream — returns a 60-min-valid listenKey.

        The caller is responsible for opening the WebSocket and calling
        :meth:`keepalive_listen_key` every ~30 min. Closing via
        :meth:`close_listen_key` is best practice but not required (Binance
        expires the key automatically after 60 min of inactivity).
        """
        if not self.api_key:
            raise RuntimeError("Binance API key required to create a listenKey")
        data = self._public_request("POST", "/api/v3/userDataStream")
        if "listenKey" not in data:
            raise RuntimeError(f"Binance create_listen_key bad response: {data}")
        return data["listenKey"]

    def keepalive_listen_key(self, listen_key: str) -> None:
        """PUT /api/v3/userDataStream?listenKey=X — extends the 60-min TTL.

        Call every ~30 min from the WS consumer thread to keep the stream
        alive. Silently no-ops on success (Binance returns ``{}``).
        """
        if not self.api_key:
            raise RuntimeError("Binance API key required for keepalive")
        self._public_request("PUT", f"/api/v3/userDataStream?listenKey={listen_key}")

    def close_listen_key(self, listen_key: str) -> None:
        """DELETE /api/v3/userDataStream?listenKey=X — closes the stream."""
        if not self.api_key:
            raise RuntimeError("Binance API key required to close listenKey")
        self._public_request("DELETE", f"/api/v3/userDataStream?listenKey={listen_key}")

    def user_data_stream_url(self, listen_key: str) -> str:
        """WebSocket URL for the given listenKey (prod or testnet)."""
        return f"{self.ws_base}/{listen_key}"

    def get_balance(self) -> Dict[str, float]:
        """
        Retrieve balances for all assets via GET /api/v3/account.

        Returns:
            Dict mapping asset symbol to free (spendable) balance.
            Only assets with free > 0 OR locked > 0 are included.

        Raises:
            RuntimeError: on missing credentials or API error
        """
        if not self.api_key or not self.api_secret:
            raise RuntimeError("Binance API credentials required for balance retrieval")

        data = self._signed_request("GET", "/api/v3/account")

        return {
            b["asset"]: float(b["free"])
            for b in data.get("balances", [])
            if float(b["free"]) > 0 or float(b["locked"]) > 0
        }

    def get_order_status(self, order_id: str) -> OrderResult:
        """
        Get status of an existing order via GET /api/v3/order.

        Args:
            order_id: 'SYMBOL:NUMERIC_ID' as returned by place_order
                      e.g. 'BTCUSDT:123456789'

        Returns:
            OrderResult with current status

        Raises:
            RuntimeError: on missing credentials or API error
            ValueError: if order_id not in 'SYMBOL:ID' format
        """
        if not self.api_key or not self.api_secret:
            raise RuntimeError("Binance API credentials required for order status")

        if ":" not in str(order_id):
            raise ValueError(
                "Binance order lookup requires 'SYMBOL:ORDER_ID' format "
                "(as returned by place_order). Got: " + str(order_id)
            )

        binance_symbol, numeric_id = str(order_id).split(":", 1)

        data = self._signed_request(
            "GET",
            "/api/v3/order",
            {"symbol": binance_symbol, "orderId": int(numeric_id)},
        )

        symbol = binance_symbol.replace("USDT", "-USD")

        return OrderResult(
            order_id=order_id,
            symbol=symbol,
            side=data["side"].lower(),
            amount=float(data.get("executedQty", 0)),
            price=float(data.get("price", 0)),
            status=data.get("status", "UNKNOWN").lower(),
            exchange="binance",
            timestamp=data.get("time", time.time() * 1000) / 1000,
        )

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order via DELETE /api/v3/order.

        Args:
            order_id: 'SYMBOL:NUMERIC_ID' as returned by place_order

        Returns:
            True if successfully cancelled.
            False if order already filled or unknown (error -2011).

        Raises:
            RuntimeError: on missing credentials or unexpected API error
            ValueError: if order_id not in 'SYMBOL:ID' format
        """
        if not self.api_key or not self.api_secret:
            raise RuntimeError(
                "Binance API credentials required for order cancellation"
            )

        if ":" not in str(order_id):
            raise ValueError(
                "Binance cancel requires 'SYMBOL:ORDER_ID' format. Got: "
                + str(order_id)
            )

        binance_symbol, numeric_id = str(order_id).split(":", 1)

        try:
            data = self._signed_request(
                "DELETE",
                "/api/v3/order",
                {"symbol": binance_symbol, "orderId": int(numeric_id)},
            )
            return data.get("status") in ("CANCELED", "CANCELLED")
        except RuntimeError as exc:
            if "-2011" in str(exc):
                # Order unknown: already filled or previously cancelled
                return False
            raise

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
