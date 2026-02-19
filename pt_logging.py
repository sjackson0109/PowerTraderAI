"""
Secure logging system for PowerTrader AI.
Provides safe logging with credential filtering and structured error handling.
"""
import logging
import os
import re
import sys
import time
from typing import Any, Dict, Optional
from logging.handlers import RotatingFileHandler


class SecureFormatter(logging.Formatter):
    """Custom formatter that filters sensitive information from logs."""
    
    # Patterns for sensitive information
    SENSITIVE_PATTERNS = [
        re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?([a-zA-Z0-9]{10,})["\']?', re.IGNORECASE),
        re.compile(r'secret["\']?\s*[:=]\s*["\']?([a-zA-Z0-9+/=]{20,})["\']?', re.IGNORECASE),
        re.compile(r'password["\']?\s*[:=]\s*["\']?([^"\'\s]{6,})["\']?', re.IGNORECASE),
        re.compile(r'token["\']?\s*[:=]\s*["\']?([a-zA-Z0-9+/=]{15,})["\']?', re.IGNORECASE),
        re.compile(r'x-api-key["\']?\s*[:=]\s*["\']?([a-zA-Z0-9]{10,})["\']?', re.IGNORECASE),
        re.compile(r'x-signature["\']?\s*[:=]\s*["\']?([a-zA-Z0-9+/=]{20,})["\']?', re.IGNORECASE),
    ]
    
    def format(self, record):
        # Format the message normally
        message = super().format(record)
        
        # Filter out sensitive information
        for pattern in self.SENSITIVE_PATTERNS:
            message = pattern.sub(lambda m: m.group(0).replace(m.group(1), '*' * 8), message)
        
        return message


class SecurityLogFilter(logging.Filter):
    """Filter to catch and sanitize security-related log entries."""
    
    def filter(self, record):
        # Convert args to strings safely
        if hasattr(record, 'args') and record.args:
            safe_args = []
            for arg in record.args:
                if isinstance(arg, (dict, list)) and len(str(arg)) > 1000:
                    safe_args.append('<large_object_redacted>')
                else:
                    safe_args.append(arg)
            record.args = tuple(safe_args)
        
        # Limit message length
        if hasattr(record, 'getMessage'):
            message = record.getMessage()
            if len(message) > 2000:
                record.msg = message[:2000] + '... [truncated]'
                record.args = ()
        
        return True


class SecureLogger:
    """Secure logger implementation for PowerTrader AI."""
    
    def __init__(self, name: str = "PowerTrader", log_dir: str = None):
        self.name = name
        self.log_dir = log_dir or os.path.join(os.path.dirname(__file__), 'logs')
        self._ensure_log_directory()
        
        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers = []
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = SecureFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(SecurityLogFilter())
        self.logger.addHandler(console_handler)
        
        # File handler with rotation
        file_handler = RotatingFileHandler(
            os.path.join(self.log_dir, f'{name.lower()}.log'),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = SecureFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(SecurityLogFilter())
        self.logger.addHandler(file_handler)
        
        # Error file handler
        error_handler = RotatingFileHandler(
            os.path.join(self.log_dir, f'{name.lower()}_error.log'),
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        error_handler.addFilter(SecurityLogFilter())
        self.logger.addHandler(error_handler)
        
        # Set file permissions
        self._set_secure_permissions()
    
    def _ensure_log_directory(self):
        """Create log directory if it doesn't exist."""
        try:
            if not os.path.exists(self.log_dir):
                os.makedirs(self.log_dir, mode=0o750)
        except OSError:
            # Fallback to current directory
            self.log_dir = os.path.dirname(__file__)
    
    def _set_secure_permissions(self):
        """Set secure permissions on log files."""
        try:
            for handler in self.logger.handlers:
                if hasattr(handler, 'baseFilename'):
                    if os.path.exists(handler.baseFilename):
                        os.chmod(handler.baseFilename, 0o640)
        except OSError:
            pass
    
    def info(self, message: str, *args, **kwargs):
        """Log info message."""
        self.logger.info(message, *args, **kwargs)
    
    def debug(self, message: str, *args, **kwargs):
        """Log debug message."""
        self.logger.debug(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Log warning message."""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Log error message."""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """Log critical message."""
        self.logger.critical(message, *args, **kwargs)
    
    def log_trade_action(self, action: str, symbol: str, details: Dict[str, Any]):
        """Log trading actions with structured format."""
        # Sanitize details to prevent sensitive data leakage
        safe_details = {}
        for key, value in details.items():
            if key.lower() in ['api_key', 'secret', 'signature', 'token', 'password']:
                safe_details[key] = '***REDACTED***'
            elif isinstance(value, str) and len(value) > 200:
                safe_details[key] = value[:200] + '...[truncated]'
            else:
                safe_details[key] = value
        
        self.info(f"TRADE_ACTION: {action} | Symbol: {symbol} | Details: {safe_details}")
    
    def log_api_call(self, method: str, endpoint: str, status_code: Optional[int] = None, 
                     response_size: Optional[int] = None):
        """Log API calls without exposing sensitive data."""
        # Remove sensitive parts from endpoint
        clean_endpoint = re.sub(r'([?&]api_key=)[^&]*', r'\1***', endpoint)
        clean_endpoint = re.sub(r'([?&]signature=)[^&]*', r'\1***', clean_endpoint)
        
        message = f"API_CALL: {method} {clean_endpoint}"
        if status_code is not None:
            message += f" | Status: {status_code}"
        if response_size is not None:
            message += f" | Size: {response_size}b"
        
        if status_code and status_code >= 400:
            self.error(message)
        else:
            self.debug(message)
    
    def log_security_event(self, event_type: str, description: str, details: Dict[str, Any] = None):
        """Log security-related events."""
        message = f"SECURITY: {event_type} | {description}"
        if details:
            # Ensure no sensitive data in security logs
            safe_details = {k: v for k, v in details.items() 
                          if k.lower() not in ['password', 'key', 'secret', 'token']}
            message += f" | Details: {safe_details}"
        
        self.warning(message)


class SafeExceptionHandler:
    """Safe exception handling with secure logging."""
    
    def __init__(self, logger: SecureLogger):
        self.logger = logger
    
    def handle_exception(self, exception: Exception, context: str = "", 
                        additional_info: Dict[str, Any] = None) -> str:
        """
        Handle exceptions safely with logging.
        
        Returns:
            Safe error message for user display
        """
        # Generate safe error message
        safe_message = self._generate_safe_error_message(exception, context)
        
        # Log detailed error (with sanitization)
        error_details = {
            'exception_type': type(exception).__name__,
            'context': context,
            'safe_message': safe_message,
        }
        
        if additional_info:
            # Filter out sensitive info from additional details
            safe_info = {k: v for k, v in additional_info.items() 
                        if k.lower() not in ['password', 'key', 'secret', 'token', 'api_key']}
            error_details.update(safe_info)
        
        self.logger.error(f"Exception in {context}: {safe_message}", exc_info=True, 
                         extra={'error_details': error_details})
        
        return safe_message
    
    def _generate_safe_error_message(self, exception: Exception, context: str) -> str:
        """Generate user-safe error message."""
        error_type = type(exception).__name__
        
        # Map internal exceptions to user-friendly messages
        safe_messages = {
            'requests.ConnectionError': 'Network connection error. Please check your internet connection.',
            'requests.Timeout': 'Request timed out. Please try again later.',
            'requests.HTTPError': 'API service error. Please try again later.',
            'json.JSONDecodeError': 'Invalid data received from service.',
            'ValidationError': str(exception),  # Our validation errors are already safe
            'FileNotFoundError': 'Required configuration file not found.',
            'PermissionError': 'File access permission denied.',
            'ValueError': 'Invalid data format encountered.',
            'TypeError': 'Data type error occurred.',
        }
        
        # Check for specific known error patterns
        error_message = str(exception).lower()
        if 'auth' in error_message or 'credential' in error_message:
            return 'Authentication error. Please check your API credentials.'
        elif 'network' in error_message or 'connection' in error_message:
            return 'Network error. Please check your connection and try again.'
        elif 'timeout' in error_message:
            return 'Operation timed out. Please try again later.'
        
        # Use mapped message or generic fallback
        return safe_messages.get(error_type, 'An unexpected error occurred. Please try again.')


# Global logger instance
_global_logger: Optional[SecureLogger] = None


def get_logger(name: str = "PowerTrader") -> SecureLogger:
    """Get global secure logger instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = SecureLogger(name)
    return _global_logger


def get_exception_handler() -> SafeExceptionHandler:
    """Get exception handler with secure logging."""
    return SafeExceptionHandler(get_logger())


def log_startup_info(component: str, version: str = "1.0"):
    """Log component startup information."""
    logger = get_logger()
    logger.info(f"Starting {component} v{version}")
    logger.info(f"Python version: {sys.version.split()[0]}")
    logger.info(f"Working directory: {os.getcwd()}")


def log_shutdown_info(component: str):
    """Log component shutdown information."""
    logger = get_logger()
    logger.info(f"Shutting down {component}")