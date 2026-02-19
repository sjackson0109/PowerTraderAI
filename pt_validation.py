"""
Input validation and sanitization for PowerTrader AI.
Provides comprehensive validation for external data sources and user inputs.
"""
import re
import json
from typing import Any, Dict, List, Optional, Union
from decimal import Decimal, InvalidOperation


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


class InputValidator:
    """Comprehensive input validation for trading data."""
    
    # Valid cryptocurrency symbols pattern
    CRYPTO_SYMBOL_PATTERN = re.compile(r'^[A-Z]{2,10}$')
    
    # Valid trading pair pattern (e.g., BTC-USD, ETH-USDT)
    TRADING_PAIR_PATTERN = re.compile(r'^[A-Z]{2,10}-[A-Z]{2,10}$')
    
    # Price validation limits (reasonable bounds for crypto prices)
    MIN_PRICE = Decimal('0.00000001')  # 1 satoshi equivalent
    MAX_PRICE = Decimal('10000000')    # 10 million USD
    
    # Volume validation limits
    MIN_VOLUME = Decimal('0.00000001')
    MAX_VOLUME = Decimal('1000000000')  # 1 billion units
    
    # Percentage limits
    MIN_PERCENTAGE = Decimal('-100')
    MAX_PERCENTAGE = Decimal('10000')  # 100x gain max
    
    @staticmethod
    def validate_crypto_symbol(symbol: Any) -> str:
        """Validate cryptocurrency symbol format."""
        if not isinstance(symbol, str):
            raise ValidationError(f"Symbol must be string, got {type(symbol)}")
        
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValidationError("Symbol cannot be empty")
        
        if not InputValidator.CRYPTO_SYMBOL_PATTERN.match(symbol):
            raise ValidationError(f"Invalid symbol format: {symbol}")
        
        return symbol
    
    @staticmethod
    def validate_trading_pair(pair: Any) -> str:
        """Validate trading pair format."""
        if not isinstance(pair, str):
            raise ValidationError(f"Trading pair must be string, got {type(pair)}")
        
        pair = pair.strip().upper()
        if not pair:
            raise ValidationError("Trading pair cannot be empty")
        
        if not InputValidator.TRADING_PAIR_PATTERN.match(pair):
            raise ValidationError(f"Invalid trading pair format: {pair}")
        
        return pair
    
    @staticmethod
    def validate_price(price: Any, field_name: str = "price") -> Decimal:
        """Validate price value."""
        try:
            if isinstance(price, str):
                price = price.strip()
                if not price:
                    raise ValidationError(f"{field_name} cannot be empty")
            
            decimal_price = Decimal(str(price))
            
            if decimal_price <= 0:
                raise ValidationError(f"{field_name} must be positive")
            
            if decimal_price < InputValidator.MIN_PRICE:
                raise ValidationError(f"{field_name} too small: {decimal_price}")
            
            if decimal_price > InputValidator.MAX_PRICE:
                raise ValidationError(f"{field_name} too large: {decimal_price}")
            
            return decimal_price
            
        except (ValueError, InvalidOperation) as e:
            raise ValidationError(f"Invalid {field_name} format: {price}")
    
    @staticmethod
    def validate_volume(volume: Any, field_name: str = "volume") -> Decimal:
        """Validate volume value."""
        try:
            if isinstance(volume, str):
                volume = volume.strip()
                if not volume:
                    raise ValidationError(f"{field_name} cannot be empty")
            
            decimal_volume = Decimal(str(volume))
            
            if decimal_volume < 0:
                raise ValidationError(f"{field_name} cannot be negative")
            
            if decimal_volume > InputValidator.MAX_VOLUME:
                raise ValidationError(f"{field_name} too large: {decimal_volume}")
            
            return decimal_volume
            
        except (ValueError, InvalidOperation) as e:
            raise ValidationError(f"Invalid {field_name} format: {volume}")
    
    @staticmethod
    def validate_percentage(percentage: Any, field_name: str = "percentage") -> Decimal:
        """Validate percentage value."""
        try:
            if isinstance(percentage, str):
                percentage = percentage.strip().replace('%', '')
                if not percentage:
                    raise ValidationError(f"{field_name} cannot be empty")
            
            decimal_pct = Decimal(str(percentage))
            
            if decimal_pct < InputValidator.MIN_PERCENTAGE:
                raise ValidationError(f"{field_name} too low: {decimal_pct}%")
            
            if decimal_pct > InputValidator.MAX_PERCENTAGE:
                raise ValidationError(f"{field_name} too high: {decimal_pct}%")
            
            return decimal_pct
            
        except (ValueError, InvalidOperation) as e:
            raise ValidationError(f"Invalid {field_name} format: {percentage}")
    
    @staticmethod
    def validate_timestamp(timestamp: Any, field_name: str = "timestamp") -> int:
        """Validate Unix timestamp."""
        try:
            if isinstance(timestamp, str):
                timestamp = timestamp.strip()
                if not timestamp:
                    raise ValidationError(f"{field_name} cannot be empty")
            
            int_timestamp = int(float(timestamp))
            
            # Reasonable bounds: 2020 to 2050
            if int_timestamp < 1577836800:  # 2020-01-01
                raise ValidationError(f"{field_name} too old: {int_timestamp}")
            
            if int_timestamp > 2524608000:  # 2050-01-01
                raise ValidationError(f"{field_name} too far in future: {int_timestamp}")
            
            return int_timestamp
            
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Invalid {field_name} format: {timestamp}")
    
    @staticmethod
    def validate_order_data(order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate trading order data structure."""
        if not isinstance(order_data, dict):
            raise ValidationError("Order data must be a dictionary")
        
        validated = {}
        
        # Required fields
        required_fields = ['id', 'symbol', 'price', 'quantity', 'side']
        for field in required_fields:
            if field not in order_data:
                raise ValidationError(f"Missing required field: {field}")
        
        # Validate ID
        order_id = order_data.get('id')
        if not isinstance(order_id, (str, int)):
            raise ValidationError("Order ID must be string or integer")
        validated['id'] = str(order_id).strip()
        
        # Validate symbol
        validated['symbol'] = InputValidator.validate_trading_pair(order_data['symbol'])
        
        # Validate price
        validated['price'] = InputValidator.validate_price(order_data['price'])
        
        # Validate quantity
        validated['quantity'] = InputValidator.validate_volume(order_data['quantity'], 'quantity')
        
        # Validate side
        side = order_data.get('side', '').strip().lower()
        if side not in ['buy', 'sell']:
            raise ValidationError(f"Invalid order side: {side}")
        validated['side'] = side
        
        # Optional fields
        if 'created_at' in order_data:
            validated['created_at'] = InputValidator.validate_timestamp(order_data['created_at'])
        
        if 'status' in order_data:
            status = str(order_data['status']).strip().lower()
            valid_statuses = ['pending', 'filled', 'cancelled', 'rejected', 'partial']
            if status not in valid_statuses:
                raise ValidationError(f"Invalid order status: {status}")
            validated['status'] = status
        
        return validated
    
    @staticmethod
    def validate_market_data(market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate market data structure from external APIs."""
        if not isinstance(market_data, dict):
            raise ValidationError("Market data must be a dictionary")
        
        validated = {}
        
        # Validate symbol if present
        if 'symbol' in market_data:
            validated['symbol'] = InputValidator.validate_trading_pair(market_data['symbol'])
        
        # Validate prices
        price_fields = ['price', 'open', 'high', 'low', 'close', 'ask', 'bid']
        for field in price_fields:
            if field in market_data and market_data[field] is not None:
                validated[field] = InputValidator.validate_price(market_data[field], field)
        
        # Validate volumes
        volume_fields = ['volume', 'base_volume', 'quote_volume']
        for field in volume_fields:
            if field in market_data and market_data[field] is not None:
                validated[field] = InputValidator.validate_volume(market_data[field], field)
        
        # Validate timestamp
        if 'timestamp' in market_data:
            validated['timestamp'] = InputValidator.validate_timestamp(market_data['timestamp'])
        
        return validated
    
    @staticmethod
    def sanitize_string(input_str: Any, max_length: int = 1000) -> str:
        """Sanitize string input to prevent injection attacks."""
        if not isinstance(input_str, str):
            input_str = str(input_str)
        
        # Remove null bytes and control characters
        sanitized = ''.join(char for char in input_str if ord(char) >= 32 or char in '\n\r\t')
        
        # Limit length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        return sanitized.strip()
    
    @staticmethod
    def validate_config_data(config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate configuration file data."""
        if not isinstance(config_data, dict):
            raise ValidationError("Config data must be a dictionary")
        
        validated = {}
        
        # Validate coins list
        if 'coins' in config_data:
            coins = config_data['coins']
            if not isinstance(coins, list):
                raise ValidationError("Coins must be a list")
            
            validated_coins = []
            for coin in coins:
                try:
                    validated_coin = InputValidator.validate_crypto_symbol(coin)
                    validated_coins.append(validated_coin)
                except ValidationError:
                    continue  # Skip invalid coins
            
            if not validated_coins:
                raise ValidationError("No valid coins found in configuration")
            
            validated['coins'] = validated_coins
        
        # Validate numeric settings
        numeric_fields = {
            'trade_start_level': (1, 10),
            'start_allocation_pct': (0.0001, 1.0),
            'dca_multiplier': (0.1, 10.0),
            'max_dca_buys_per_24h': (0, 100),
            'pm_start_pct_no_dca': (0.1, 100.0),
            'pm_start_pct_with_dca': (0.1, 100.0),
            'trailing_gap_pct': (0.1, 10.0)
        }
        
        for field, (min_val, max_val) in numeric_fields.items():
            if field in config_data:
                try:
                    value = float(config_data[field])
                    if value < min_val or value > max_val:
                        raise ValidationError(f"{field} must be between {min_val} and {max_val}")
                    validated[field] = value
                except (ValueError, TypeError):
                    raise ValidationError(f"Invalid {field} format")
        
        # Validate DCA levels
        if 'dca_levels' in config_data:
            dca_levels = config_data['dca_levels']
            if not isinstance(dca_levels, list):
                raise ValidationError("DCA levels must be a list")
            
            validated_levels = []
            for level in dca_levels:
                try:
                    level_val = float(level)
                    if level_val > 0:  # DCA levels should be negative (losses)
                        level_val = -level_val
                    if level_val < -90:  # Reasonable limit
                        continue
                    validated_levels.append(level_val)
                except (ValueError, TypeError):
                    continue
            
            validated['dca_levels'] = sorted(validated_levels, reverse=True)  # Sort from highest to lowest
        
        # Validate directory path
        if 'main_neural_dir' in config_data:
            dir_path = config_data['main_neural_dir']
            if dir_path is not None:
                validated['main_neural_dir'] = InputValidator.sanitize_string(dir_path, 500)
        
        return validated


def safe_json_loads(json_str: str, max_size: int = 1024*1024) -> Dict[str, Any]:
    """Safely parse JSON with size limits and error handling."""
    if not isinstance(json_str, str):
        raise ValidationError("JSON input must be string")
    
    if len(json_str) > max_size:
        raise ValidationError(f"JSON too large: {len(json_str)} bytes")
    
    try:
        data = json.loads(json_str)
        if not isinstance(data, dict):
            raise ValidationError("JSON must represent an object")
        return data
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON format: {e}")


def validate_api_response(response_data: Any, expected_fields: List[str] = None) -> Dict[str, Any]:
    """Validate API response structure and content."""
    if not isinstance(response_data, dict):
        raise ValidationError("API response must be a dictionary")
    
    # Check for error indicators
    if 'error' in response_data:
        error_msg = InputValidator.sanitize_string(str(response_data['error']), 200)
        raise ValidationError(f"API error: {error_msg}")
    
    validated = {}
    
    # Validate expected fields if provided
    if expected_fields:
        for field in expected_fields:
            if field not in response_data:
                raise ValidationError(f"Missing expected field: {field}")
            validated[field] = response_data[field]
    
    # Add other fields with basic validation
    for key, value in response_data.items():
        if key not in validated:
            if isinstance(value, str):
                validated[key] = InputValidator.sanitize_string(value)
            elif isinstance(value, (int, float)):
                validated[key] = value
            elif isinstance(value, (list, dict)):
                validated[key] = value  # Keep as-is for complex structures
    
    return validated