# Troubleshooting Guide

Common issues and solutions for PowerTraderAI+ setup, configuration, and operation.

## Quick Emergency Procedures

### Emergency Stop Trading
If you need to immediately halt all trading:

```
IMMEDIATE ACTIONS:
1. Click "Emergency Stop" button (red button in main interface)
2. OR press Ctrl + Alt + S
3. OR close PowerTraderAI+ application completely
4. Log into Robinhood app/website to verify all orders are cancelled
```

### System Recovery
If PowerTraderAI+ crashes or becomes unresponsive:

```powershell
# Force close if needed
taskkill /f /im python.exe

# Restart application
cd C:\Users\Administrator\PowerTrader\PowerTrader_AI
python pt_hub.py

# Check logs for error details
type logs\powertrader.log | findstr ERROR
```

## Common Issues Index

- [Installation Problems](#installation-problems)
- [API Connection Issues](#api-connection-issues)
- [Authentication Failures](#authentication-failures)
- [Trading Execution Issues](#trading-execution-issues)
- [Data/Chart Problems](#data-and-chart-problems)
- [Performance Issues](#performance-issues)
- [Security and Credential Issues](#security-and-credential-issues)

## Installation Problems

### Issue: Python Not Found
```
Error: 'python' is not recognized as an internal or external command
```

**Solutions:**
1. **Add Python to PATH**:
   ```powershell
   # Check if Python is installed
   where python
   
   # If not found, add to PATH manually
   setx PATH "%PATH%;C:\Python39;C:\Python39\Scripts"
   
   # Restart command prompt and test
   python --version
   ```

2. **Reinstall Python**:
   - Download from [python.org](https://python.org)
   - Check "Add Python to PATH" during installation
   - Select "Install for all users"

### Issue: Module Not Found Errors
```
ModuleNotFoundError: No module named 'requests'
```

**Solutions:**
1. **Install Requirements**:
   ```bash
   # Upgrade pip first
   python -m pip install --upgrade pip
   
   # Install all requirements
   pip install -r requirements.txt
   
   # Verify installation
   pip list
   ```

2. **Virtual Environment Issues**:
   ```bash
   # Create new virtual environment
   python -m venv powertrader_env
   
   # Activate environment
   powertrader_env\Scripts\activate
   
   # Install requirements in environment
   pip install -r requirements.txt
   ```

### Issue: Permission Denied
```
PermissionError: [Errno 13] Permission denied
```

**Solutions:**
1. **Run as Administrator**:
   - Right-click Command Prompt
   - Select "Run as administrator"
   - Navigate to PowerTraderAI+ folder
   - Run installation commands

2. **User Permissions**:
   ```powershell
   # Give user full control over PowerTrader folder
   icacls "C:\PowerTraderAI" /grant "%USERNAME%:F" /t
   ```

## API Connection Issues

### Issue: KuCoin Connection Failed
```
Error: Failed to connect to KuCoin API
```

**Diagnosis Steps:**
1. **Check Internet Connection**:
   ```bash
   ping api.kucoin.com
   ```

2. **Verify API Credentials**:
   ```python
   # Test credentials manually
   import requests
   
   headers = {
       'KC-API-KEY': 'your_api_key',
       'KC-API-PASSPHRASE': 'your_passphrase'
   }
   
   response = requests.get('https://api.kucoin.com/api/v1/timestamp', headers=headers)
   print(response.status_code, response.text)
   ```

**Solutions:**
1. **Regenerate API Keys**:
   - Log into KuCoin
   - Delete existing API key
   - Create new API key with correct permissions
   - Update PowerTraderAI+ configuration

2. **Check Firewall**:
   ```powershell
   # Allow Python through firewall
   netsh advfirewall firewall add rule name="PowerTraderAI+" dir=out action=allow program="C:\Python39\python.exe"
   ```

3. **IP Restrictions**:
   - Check if your IP changed
   - Update IP whitelist in KuCoin settings
   - Or disable IP restrictions temporarily

### Issue: Robinhood Login Failed
```
Error: Invalid username or password
```

**Solutions:**
1. **Verify Credentials**:
   - Test login in Robinhood app/website
   - Ensure 2FA is working correctly
   - Check for account lockouts

2. **Clear Stored Credentials**:
   ```python
   # Clear cached Robinhood credentials
   from pt_trader import clear_credentials
   clear_credentials()
   
   # Re-authenticate
   from pt_trader import authenticate
   authenticate()
   ```

3. **Device Token Issues**:
   ```python
   # Reset device registration
   from pt_trader import reset_device_token
   reset_device_token()
   ```

## Authentication Failures

### Issue: 2FA Code Not Working
```
Error: Two-factor authentication failed
```

**Solutions:**
1. **Check Time Sync**:
   ```powershell
   # Sync system clock
   w32tm /resync
   
   # Verify time
   time
   ```

2. **Regenerate 2FA**:
   - Disable 2FA in exchange settings
   - Re-enable with new QR code
   - Update authenticator app

3. **Backup Codes**:
   - Use backup/recovery codes
   - Generate new backup codes
   - Store securely

### Issue: API Key Permissions Error
```
Error: Insufficient permissions for this operation
```

**Solutions:**
1. **Check API Permissions**:
   ```
   KuCoin Required Permissions:
   - General - REQUIRED
   - Trade - NOT needed for market data
   - Transfer - NOT needed
   ```

2. **Robinhood Permissions**:
   - Ensure crypto trading is enabled
   - Complete account verification
   - Check for trading restrictions

## Trading Execution Issues

### Issue: Orders Not Executing
```
Error: Order failed to execute
```

**Diagnosis:**
1. **Check Account Balance**:
   ```python
   from pt_trader import get_account_balance
   balance = get_account_balance()
   print(f"Available funds: ${balance}")
   ```

2. **Verify Market Hours**:
   - Crypto: 24/7 trading available
   - Check exchange maintenance schedules

**Solutions:**
1. **Insufficient Funds**:
   - Add funds to Robinhood account
   - Wait for deposits to settle
   - Check for pending orders

2. **Order Size Issues**:
   - Reduce order size below account limits
   - Check minimum order requirements
   - Verify cryptocurrency availability

3. **Market Conditions**:
   - High volatility may affect execution
   - Use limit orders instead of market orders
   - Check for trading halts

### Issue: Portfolio Sync Problems
```
Error: Portfolio data inconsistent
```

**Solutions:**
1. **Force Sync**:
   ```python
   from pt_trader import sync_portfolio
   sync_portfolio(force=True)
   ```

2. **Clear Cache**:
   ```python
   from pt_trader import clear_cache
   clear_cache()
   ```

## Data and Chart Problems

### Issue: Charts Not Loading
```
Error: Unable to load chart data
```

**Solutions:**
1. **Check Data Connection**:
   ```python
   # Test KuCoin data feed
   from pt_thinker import test_data_feed
   test_data_feed()
   ```

2. **Clear Chart Cache**:
   ```python
   # Clear cached chart data
   from pt_hub import clear_chart_cache
   clear_chart_cache()
   ```

3. **Reduce Chart Frequency**:
   - Increase update interval in settings
   - Lower chart resolution temporarily

### Issue: Incorrect Price Data
```
Error: Price data appears incorrect
```

**Solutions:**
1. **Data Validation**:
   ```python
   from pt_validation import validate_price_data
   issues = validate_price_data()
   print(issues)
   ```

2. **Multiple Data Sources**:
   - Compare with KuCoin website
   - Check other exchanges for reference
   - Report data quality issues

## Performance Issues

### Issue: Application Running Slowly
```
Symptom: GUI freezing or slow response
```

**Solutions:**
1. **Check System Resources**:
   ```powershell
   # Monitor CPU and memory usage
   tasklist /fi "imagename eq python.exe"
   
   # Check available memory
   systeminfo | findstr "Available Physical Memory"
   ```

2. **Optimize Settings**:
   ```json
   {
     "performance": {
       "chart_update_interval": 5,
       "data_cache_size": 1000,
       "max_concurrent_requests": 5,
       "enable_data_compression": true
     }
   }
   ```

3. **Background Processes**:
   - Close unnecessary applications
   - Disable real-time antivirus scanning for PowerTrader folder
   - Use Task Manager to identify resource hogs

### Issue: High Memory Usage
```
Symptom: Python process using excessive memory
```

**Solutions:**
1. **Memory Optimization**:
   ```python
   # Enable memory optimization
   from pt_performance import optimize_memory
   optimize_memory()
   ```

2. **Restart Application**:
   - Close PowerTraderAI+
   - Clear system cache
   - Restart application

## Security and Credential Issues

### Issue: Credentials File Corrupted
```
Error: Unable to decrypt credentials
```

**Solutions:**
1. **Restore from Backup**:
   ```python
   from pt_security import restore_credentials
   restore_credentials(backup_file='credentials_backup.enc')
   ```

2. **Re-enter Credentials**:
   ```python
   # Clear corrupted credentials
   from pt_security import clear_all_credentials
   clear_all_credentials()
   
   # Re-configure through GUI
   ```

### Issue: Encryption Key Lost
```
Error: Master encryption key not found
```

**Solutions:**
1. **Use Backup Key**:
   - Locate backup encryption key
   - Restore from secure storage

2. **Reset All Credentials** (Last Resort):
   ```python
   # WARNING: This clears ALL saved credentials
   from pt_security import factory_reset_credentials
   factory_reset_credentials()
   ```

## Diagnostic Tools

### Built-in Diagnostics

#### System Health Check
```python
# Run comprehensive system diagnostics
from pt_diagnostics import SystemDiagnostics

diag = SystemDiagnostics()
report = diag.run_full_diagnostic()
print(report)
```

#### Connection Test
```python
# Test all external connections
from pt_diagnostics import ConnectionTest

test = ConnectionTest()
results = test.test_all_connections()
for service, status in results.items():
    print(f"{service}: {status}")
```

#### Log Analysis
```python
# Analyze recent logs for issues
from pt_diagnostics import LogAnalyzer

analyzer = LogAnalyzer()
issues = analyzer.find_recent_issues(hours=24)
for issue in issues:
    print(f"Issue: {issue['type']} at {issue['timestamp']}")
```

### Manual Diagnostics

#### Log File Locations
```
PowerTraderAI/logs/
├── powertrader.log      # Main application log
├── trading.log          # Trading-specific events
├── api.log             # API communication log
├── errors.log          # Error messages only
└── security.log        # Security events
```

#### Log Analysis Commands
```powershell
# Find recent errors
findstr "ERROR" logs\powertrader.log | more

# Check API issues
findstr "API\|Connection" logs\api.log | more

# Review trading activity
findstr "Order\|Trade" logs\trading.log | more
```

## Getting Additional Help

### Support Resources

#### Documentation
- **Full Documentation**: [PowerTraderAI+ Docs](../README.md)
- **API Reference**: [API Configuration](../api-configuration/README.md)
- **Security Guide**: [Security Best Practices](../security/README.md)

#### Community Support
- **GitHub Issues**: [Report bugs and issues](https://github.com/sjackson0109/PowerTraderAI/issues)
- **Discussions**: Community Q&A and tips
- **Wiki**: User-contributed guides and solutions

#### Professional Support
- **Email Support**: Technical assistance for complex issues
- **Remote Assistance**: Screen sharing for difficult problems
- **Custom Configuration**: Professional setup services

### Before Contacting Support

#### Information to Gather
1. **System Information**:
   ```powershell
   # System details
   systeminfo | findstr "OS\|Version\|Memory"
   
   # Python version
   python --version
   
   # PowerTraderAI+ version
   python -c "import pt_hub; print(pt_hub.__version__)"
   ```

2. **Error Messages**:
   - Copy exact error messages
   - Include timestamps
   - Note what you were doing when error occurred

3. **Log Files**:
   - Recent entries from relevant log files
   - Any stack traces or detailed error information

4. **Configuration**:
   - Anonymized configuration files (remove credentials)
   - Settings that may be relevant to the issue

#### Issue Template
```markdown
**PowerTraderAI+ Version**: [version]
**Operating System**: [OS and version]
**Python Version**: [version]

**Problem Description**:
[Detailed description of the issue]

**Steps to Reproduce**:
1. [Step 1]
2. [Step 2]
3. [Error occurs]

**Expected Behavior**:
[What should happen]

**Actual Behavior**:
[What actually happens]

**Error Messages**:
[Exact error messages]

**Log Entries**:
[Relevant log entries]

**Additional Context**:
[Any other relevant information]
```

## Prevention and Best Practices

### Regular Maintenance

#### Daily Checks
- [ ] Verify application starts correctly
- [ ] Check data feeds are updating
- [ ] Review recent trades and orders
- [ ] Monitor account balances

#### Weekly Maintenance
- [ ] Review error logs
- [ ] Check system performance
- [ ] Verify backup procedures
- [ ] Update any expired API keys

#### Monthly Reviews
- [ ] Performance optimization
- [ ] Security audit
- [ ] Configuration review
- [ ] Software updates

### Monitoring Setup

#### Automated Monitoring
```python
# Set up automated health monitoring
from pt_monitoring import HealthMonitor

monitor = HealthMonitor()
monitor.enable_automated_checks()
monitor.set_alert_thresholds({
    'api_response_time': 5.0,    # seconds
    'error_rate': 0.05,          # 5% max error rate
    'memory_usage': 0.8          # 80% max memory
})
```

#### Alert Configuration
```json
{
  "alerts": {
    "email_notifications": true,
    "desktop_notifications": true,
    "log_level": "WARNING",
    "alert_types": [
      "api_failures",
      "authentication_errors", 
      "trading_failures",
      "system_errors"
    ]
  }
}
```

**Remember**: Most issues can be resolved with basic troubleshooting. When in doubt, restart the application and check the logs for detailed error information.