# API Configuration Guide

Detailed instructions for configuring API connections between PowerTraderAI+ and external services.

## API Overview

PowerTraderAI+ integrates with external services through APIs (Application Programming Interfaces). This guide covers:
- **KuCoin API**: Market data and price feeds
- **Robinhood API**: Trading execution and portfolio management
- **Configuration Management**: Secure setup and management
- **Testing and Validation**: Ensuring connections work properly

## Prerequisites

Before configuring APIs:
- [KuCoin account setup](../exchanges/kucoin-setup.md) completed
- [Robinhood account setup](../exchanges/robinhood-setup.md) completed  
- PowerTraderAI+ installed and running
- Basic security measures implemented

## Configuration Methods

### Method 1: GUI Configuration (Recommended)

1. **Launch PowerTraderAI+**:
   ```bash
   python pt_hub.py
   ```

2. **Access Settings**:
   - Menu: Settings → API Configuration
   - Or press `Ctrl + ,`

3. **Configure Each Service**:
   - Select service tab (KuCoin/Robinhood)
   - Enter credentials
   - Test connection
   - Save configuration

### Method 2: Manual Configuration Files

Advanced users can directly edit configuration files:
```
PowerTraderAI/
├── config/
│   ├── exchanges.json     # Exchange configurations
│   ├── api_settings.json  # API-specific settings
│   └── security.json      # Security configurations
```

## KuCoin API Configuration

### Step 1: Gather KuCoin Credentials

From your KuCoin account (see [KuCoin Setup Guide](../exchanges/kucoin-setup.md)):
- **API Key**: Long alphanumeric string
- **API Secret**: Even longer alphanumeric string
- **API Passphrase**: Your chosen passphrase

### Step 2: Configure in PowerTraderAI+

#### GUI Method:
1. **Open API Settings**: Settings → Exchanges → KuCoin
2. **Enter Credentials**:
   ```
   API Key: [paste your API key]
   API Secret: [paste your API secret]
   Passphrase: [enter your passphrase]
   ```
3. **Advanced Settings**:
   ```
   Environment: Production (default)
   Base URL: https://api.kucoin.com
   Timeout: 30 seconds
   Rate Limit: Respect KuCoin limits
   ```

#### Manual Configuration:
Edit `config/exchanges.json`:
```json
{
  "kucoin": {
    "api_key": "your_api_key_here",
    "api_secret": "your_api_secret_here",
    "passphrase": "your_passphrase_here",
    "environment": "live",
    "base_url": "https://api.kucoin.com",
    "timeout": 30,
    "rate_limit": {
      "requests_per_second": 10,
      "burst_limit": 100
    },
    "enabled": true
  }
}
```

### Step 3: Test KuCoin Connection

#### Automatic Test:
```
In PowerTraderAI+:
1. Click "Test Connection" button
2. Verify "Connection Successful" message
3. Check market data appears in charts
```

#### Manual Test:
```python
# Test from command line
python -c "
from pt_thinker import KuCoinClient
client = KuCoinClient()
server_time = client.get_server_time()
print(f'KuCoin server time: {server_time}')
"
```

### KuCoin Configuration Options

| Setting | Description | Default |
|---------|-------------|---------|
| `api_key` | Your KuCoin API key | Required |
| `api_secret` | Your KuCoin API secret | Required |
| `passphrase` | Your API passphrase | Required |
| `environment` | live or sandbox | live |
| `timeout` | Request timeout (seconds) | 30 |
| `rate_limit` | Requests per second | 10 |
| `retry_attempts` | Failed request retries | 3 |
| `websocket_enabled` | Real-time data stream | true |

## Robinhood API Configuration

### Step 1: Gather Robinhood Credentials

From your Robinhood account:
- **Username**: Your email address
- **Password**: Your account password
- **2FA Method**: SMS or authenticator app

### Step 2: Configure in PowerTraderAI+

#### GUI Method:
1. **Open Trading Settings**: Settings → Exchanges → Robinhood
2. **Enter Credentials**:
   ```
   Username: your_email@example.com
   Password: your_password
   2FA Method: SMS/Authenticator
   ```
3. **Security Settings**:
   ```
   Remember Login: Yes (encrypted locally)
   Session Timeout: 24 hours
   Auto-Refresh: Enabled
   ```

#### Manual Configuration:
Edit `config/exchanges.json`:
```json
{
  "robinhood": {
    "username": "your_email@example.com",
    "password": "[encrypted_password]",
    "device_token": "[auto_generated]",
    "mfa_code": null,
    "environment": "live",
    "session_timeout": 86400,
    "auto_refresh": true,
    "paper_trading": false,
    "enabled": true
  }
}
```

### Step 3: Initial Authentication

#### First-Time Setup:
1. **Start Authentication**: Click "Connect to Robinhood"
2. **Enter 2FA Code**: PowerTraderAI+ will prompt for code
3. **Device Registration**: App creates secure device token
4. **Save Configuration**: Encrypted credentials stored locally

#### Troubleshooting Authentication:
```python
# Reset Robinhood authentication
from pt_trader import reset_robinhood_auth
reset_robinhood_auth()

# Test new connection
from pt_trader import test_connection
result = test_connection()
print(result)
```

### Robinhood Configuration Options

| Setting | Description | Default |
|---------|-------------|---------|
| `username` | Robinhood email | Required |
| `password` | Account password (encrypted) | Required |
| `device_token` | Auto-generated device ID | Auto |
| `mfa_code` | Current 2FA code | Prompt |
| `session_timeout` | Login session duration | 24h |
| `paper_trading` | Demo mode (if available) | false |
| `order_timeout` | Trade order timeout | 60s |
| `retry_attempts` | Failed order retries | 3 |

## Advanced Configuration

### Environment Variables

For enhanced security, use environment variables:

```powershell
# Windows PowerShell
$env:KUCOIN_API_KEY="your_api_key"
$env:KUCOIN_API_SECRET="your_api_secret" 
$env:KUCOIN_PASSPHRASE="your_passphrase"
$env:ROBINHOOD_USERNAME="your_email"
$env:ROBINHOOD_PASSWORD="your_password"
```

PowerTraderAI+ will automatically use these if config files are empty.

### Configuration Encryption

#### Enable Encryption:
```python
# Enable config file encryption
from pt_security import ConfigEncryption
encryptor = ConfigEncryption()
encryptor.encrypt_config_files()
```

#### Encryption Settings:
```json
{
  "security": {
    "encrypt_config": true,
    "encryption_method": "AES-256",
    "key_derivation": "PBKDF2",
    "iterations": 100000
  }
}
```

### Multiple Environment Support

Configure different environments:

```json
{
  "environments": {
    "production": {
      "kucoin": { "environment": "live" },
      "robinhood": { "paper_trading": false }
    },
    "staging": {
      "kucoin": { "environment": "sandbox" },
      "robinhood": { "paper_trading": true }
    }
  },
  "active_environment": "production"
}
```

## Connection Management

### Connection Pooling

PowerTraderAI+ manages connections efficiently:
- **Connection Reuse**: Maintains persistent connections
- **Pool Management**: Limits concurrent connections
- **Health Monitoring**: Regular connection health checks
- **Automatic Recovery**: Reconnects on failures

### Rate Limiting

#### Built-in Rate Limiting:
```json
{
  "rate_limits": {
    "kucoin": {
      "requests_per_second": 10,
      "burst_allowance": 50,
      "retry_after": 1
    },
    "robinhood": {
      "requests_per_minute": 60,
      "trading_per_hour": 100,
      "cool_down": 5
    }
  }
}
```

#### Custom Rate Limiting:
```python
from pt_config import RateLimiter

# Create custom rate limiter
limiter = RateLimiter(
    requests_per_second=5,
    burst_limit=20,
    cool_down_period=10
)
```

### Error Handling

#### Retry Configuration:
```json
{
  "error_handling": {
    "max_retries": 3,
    "retry_delay": 1,
    "exponential_backoff": true,
    "circuit_breaker": {
      "failure_threshold": 5,
      "reset_timeout": 60
    }
  }
}
```

#### Error Types and Responses:
| Error Type | Action | Retry |
|------------|--------|--------|
| Network Timeout | Wait and retry | Yes |
| Rate Limit | Wait and retry | Yes |
| Authentication | Re-authenticate | Once |
| Invalid Request | Log and skip | No |
| Server Error | Wait and retry | Yes |

## Monitoring and Logging

### API Activity Monitoring

#### Real-time Monitoring:
```python
from pt_monitoring import APIMonitor

monitor = APIMonitor()
stats = monitor.get_api_statistics()
print(f"KuCoin requests: {stats['kucoin']['total_requests']}")
print(f"Robinhood requests: {stats['robinhood']['total_requests']}")
```

#### Performance Metrics:
- **Response Times**: Average API response times
- **Success Rates**: Percentage of successful requests
- **Error Rates**: Frequency of different error types
- **Data Quality**: Market data completeness and accuracy

### Logging Configuration

#### Log Levels:
```json
{
  "logging": {
    "api_calls": "INFO",
    "authentication": "INFO", 
    "errors": "ERROR",
    "data_quality": "WARNING",
    "performance": "DEBUG"
  }
}
```

#### Log Rotation:
```json
{
  "log_rotation": {
    "max_size": "100MB",
    "backup_count": 5,
    "rotation": "daily"
  }
}
```

## 🧪 Testing and Validation

### Connection Testing

#### Comprehensive Test Suite:
```python
# Run full API test suite
python scripts/test_api_connections.py

# Test specific service
python scripts/test_kucoin_api.py
python scripts/test_robinhood_api.py
```

#### Manual Testing Commands:
```python
# Test KuCoin market data
from pt_thinker import get_ticker_data
data = get_ticker_data("BTC-USDT")
print(f"BTC Price: ${data['price']}")

# Test Robinhood portfolio
from pt_trader import get_account_info
account = get_account_info()
print(f"Buying Power: ${account['buying_power']}")
```

### Data Validation

#### Market Data Validation:
```python
from pt_validation import DataValidator

validator = DataValidator()
quality_report = validator.validate_market_data()
print(f"Data Quality Score: {quality_report['score']}/100")
```

#### Portfolio Validation:
```python
from pt_validation import PortfolioValidator

validator = PortfolioValidator()
portfolio_check = validator.validate_portfolio_data()
print(f"Portfolio Sync: {portfolio_check['in_sync']}")
```

## Troubleshooting

### Common Configuration Issues

#### 1. Invalid API Credentials
```
Error: "Invalid API Key"
Solutions:
- Verify API key copied correctly (no extra spaces)
- Check API key permissions on exchange
- Ensure API key hasn't expired
- Regenerate API key if necessary
```

#### 2. Network Connectivity Issues
```
Error: "Connection timeout"
Solutions:
- Check internet connection
- Verify firewall isn't blocking PowerTraderAI+
- Test with different network (mobile hotspot)
- Check exchange status pages
```

#### 3. Rate Limiting Issues
```
Error: "Rate limit exceeded"
Solutions:
- Reduce update frequency in settings
- Check for multiple PowerTraderAI+ instances
- Wait for rate limit reset
- Contact exchange for limit increase
```

#### 4. Authentication Failures
```
Error: "Authentication failed"
Solutions:
- Verify username/password combination
- Check 2FA setup and current code
- Clear saved credentials and re-authenticate
- Update device token if expired
```

### Diagnostic Tools

#### Built-in Diagnostics:
```python
# Run comprehensive diagnostics
from pt_diagnostics import SystemDiagnostics

diagnostics = SystemDiagnostics()
report = diagnostics.run_full_diagnostic()
print(report.to_string())
```

#### Configuration Validator:
```python
# Validate configuration files
from pt_validation import ConfigValidator

validator = ConfigValidator()
issues = validator.validate_all_configs()
for issue in issues:
    print(f"Config Issue: {issue}")
```

## Security Considerations

### API Key Security

#### Best Practices:
- Store API keys encrypted at rest
- Use minimal required permissions
- Regular key rotation schedule
- Monitor API key usage logs
- Implement IP restrictions where possible

#### Security Monitoring:
```python
# Monitor API security
from pt_security import SecurityMonitor

monitor = SecurityMonitor()
security_alerts = monitor.check_api_security()
for alert in security_alerts:
    print(f"Security Alert: {alert}")
```

### Network Security

#### Secure Communication:
- All API calls use HTTPS/TLS encryption
- Certificate validation enabled
- No credential transmission over unencrypted connections
- VPN compatibility maintained

## Support and Resources

### API Documentation
- **KuCoin API Docs**: [docs.kucoin.com](https://docs.kucoin.com)
- **Robinhood API**: Internal documentation available
- **PowerTraderAI+ API Guide**: [api-reference.md](api-reference.md)

### Support Channels
- **GitHub Issues**: Technical problems and bugs
- **Community Forum**: User discussions and tips
- **Documentation**: Comprehensive guides and tutorials
- **Email Support**: Direct technical assistance

### Status Pages
- **KuCoin Status**: [status.kucoin.com](https://status.kucoin.com)
- **Robinhood Status**: [status.robinhood.com](https://status.robinhood.com)
- **PowerTraderAI+ Status**: Monitor through application logs

## Configuration Checklist

### Initial Setup
- [ ] KuCoin API keys generated and configured
- [ ] Robinhood authentication completed
- [ ] Configuration files properly formatted
- [ ] Encryption enabled for sensitive data
- [ ] Connection tests successful
- [ ] Error handling configured
- [ ] Rate limiting configured
- [ ] Logging enabled and configured

### Ongoing Maintenance
- [ ] Regular API key rotation
- [ ] Monitor rate limit usage
- [ ] Review error logs weekly
- [ ] Test backup configurations
- [ ] Update API endpoints as needed
- [ ] Monitor security alerts
- [ ] Performance optimization reviews

**Next Steps**: With API configuration complete, proceed to [User Guide](../user-guide/README.md) to start using PowerTraderAI+.