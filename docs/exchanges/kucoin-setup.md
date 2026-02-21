# KuCoin Setup Guide

Complete step-by-step guide to setting up KuCoin for market data with PowerTraderAI+.

## What is KuCoin?

KuCoin is a global cryptocurrency exchange that provides:
- **Real-time Market Data**: Live price feeds and charts
- **Historical Data**: Past price movements for AI training
- **Technical Indicators**: Built-in analysis tools
- **API Access**: Programmatic data access for trading bots

**For PowerTraderAI+**: KuCoin serves as the primary market data provider, offering reliable and fast price feeds for AI analysis and charting.

## Account Requirements

### What You'll Need
- Valid email address
- Phone number (for SMS verification)
- Government-issued ID (for account verification)
- Residential address

### Verification Levels
- **Level 1**: Email verification (sufficient for API access)
- **Level 2**: Identity verification (increases limits)
- **Level 3**: Advanced verification (highest limits)

**Note**: Level 1 verification is sufficient for PowerTraderAI+'s market data needs.

## Step-by-Step Setup

### Step 1: Create KuCoin Account

1. **Visit KuCoin**: Go to [www.kucoin.com](https://www.kucoin.com)

2. **Sign Up**:
   - Click "Sign Up" in the top right
   - Enter email address
   - Create strong password (8+ characters, mixed case, numbers, symbols)
   - Agree to Terms of Service
   - Complete CAPTCHA verification

3. **Email Verification**:
   - Check your email for verification link
   - Click verification link
   - Return to KuCoin and log in

### Step 2: Enable Two-Factor Authentication (2FA)

**Highly Recommended for Security**

1. **Access Security Settings**:
   - Log in to KuCoin
   - Go to Account → Security

2. **Set Up Google Authenticator**:
   - Download Google Authenticator app on your phone
   - Click "Enable" next to Google Authenticator
   - Scan QR code with your phone
   - Enter 6-digit code from app
   - Save backup codes in secure location

3. **SMS Verification** (Optional):
   - Add phone number for SMS backup
   - Verify with SMS code

### Step 3: Identity Verification (Optional)

**Required for higher API limits**

1. **Start Verification**:
   - Go to Account → Verification
   - Click "Verify Now" under Individual Verification

2. **Provide Information**:
   - Full name (as on ID)
   - Date of birth
   - Nationality
   - Residential address

3. **Upload Documents**:
   - Government-issued ID (passport, driver's license, national ID)
   - Take clear photos of both sides
   - Ensure all text is readable

4. **Selfie Verification**:
   - Take selfie holding your ID
   - Follow on-screen instructions
   - Ensure face and ID are clearly visible

5. **Wait for Approval**:
   - Verification typically takes 1-24 hours
   - Check email for approval notification

### Step 4: Generate API Keys

**Critical for PowerTraderAI+ Integration**

1. **Access API Management**:
   - Log in to KuCoin
   - Go to Account → API Management
   - Click "Create API"

2. **API Key Configuration**:
   ```
   API Name: PowerTraderAI+ Market Data
   Permissions:
   - General (required)
   - Trade (not needed for market data)
   - Transfer (not needed)
   - Margin (not needed)
   - Futures (not needed)
   ```

3. **Security Settings**:
   - **Passphrase**: Create a secure passphrase (save this!)
   - **IP Restriction**: Add your PowerTraderAI+ server IP (optional but recommended)
   - **Validity Period**: Set to never expire or 1+ years

4. **Complete Creation**:
   - Enter 2FA code
   - Click "Create"
   - **IMPORTANT**: Copy and securely save:
     - API Key
     - API Secret
     - API Passphrase

### Step 5: Test API Connection

**Verify Your Setup**

1. **Test Basic Connection**:
   ```bash
   # Test with curl (replace with your keys)
   curl -H "KC-API-KEY: your_api_key" \
        -H "KC-API-SIGN: signature" \
        -H "KC-API-TIMESTAMP: timestamp" \
        -H "KC-API-PASSPHRASE: your_passphrase" \
        https://api.kucoin.com/api/v1/accounts
   ```

2. **Test in PowerTraderAI+**:
   - Run PowerTraderAI+
   - Go to Settings → Exchanges → KuCoin
   - Enter your API credentials
   - Click "Test Connection"
   - Verify successful connection

## KuCoin Configuration in PowerTraderAI+

### API Settings

In PowerTraderAI+ settings:

```json
{
  "kucoin": {
    "api_key": "your_api_key_here",
    "api_secret": "your_api_secret_here",
    "passphrase": "your_passphrase_here",
    "sandbox": false,
    "timeout": 30
  }
}
```

### Market Data Settings

Configure data preferences:
- **Primary Pairs**: BTC-USDT, ETH-USDT, etc.
- **Update Frequency**: 1-5 seconds (respect rate limits)
- **Historical Data**: 30-90 days for AI training
- **Timezone**: Your local timezone

## Understanding KuCoin Data

### Available Data Types

1. **Real-time Prices**: Current bid/ask/last prices
2. **Kline/Candlestick**: OHLCV data for charting
3. **Order Book**: Market depth data
4. **Trade History**: Recent trade executions
5. **Market Stats**: 24h volume, price change

### Data Formats

KuCoin returns data in JSON format:
```json
{
  "code": "200000",
  "data": {
    "symbol": "BTC-USDT",
    "price": "45000.5",
    "time": 1640995200000,
    "changeRate": "0.0234"
  }
}
```

## Security Best Practices

### API Key Security

1. **Minimal Permissions**: Only enable "General" permission
2. **IP Whitelisting**: Restrict to your PowerTraderAI+ server
3. **Regular Rotation**: Change keys every 3-6 months
4. **Secure Storage**: Encrypt keys in PowerTraderAI+

### Account Security

1. **Strong Password**: Unique, complex password
2. **2FA Required**: Always enable Google Authenticator
3. **Regular Monitoring**: Check account activity logs
4. **Email Alerts**: Enable security notifications

## Rate Limits and Restrictions

### API Rate Limits

KuCoin enforces these limits:
- **Public Data**: 100 requests per 10 seconds
- **Private Data**: 45 requests per 10 seconds
- **WebSocket**: 100 connections per IP

### PowerTraderAI+ Optimization

PowerTraderAI+ automatically:
- Respects rate limits
- Uses WebSocket for real-time data
- Caches frequently accessed data
- Implements exponential backoff

## Costs and Fees

### API Usage
- **Market Data**: Completely free
- **Rate Limits**: No charges for standard usage
- **Premium Features**: Available with paid plans (optional)

### Trading Fees (if you trade on KuCoin)
- **Maker Fee**: 0.1%
- **Taker Fee**: 0.1%
- **Reduced Fees**: Available with KCS token holdings

**Note**: PowerTraderAI+ uses KuCoin only for data, not trading, so no trading fees apply.

## Troubleshooting

### Common Issues

**1. API Key Authentication Failed**
```
Error: Invalid API Key
Solution:
- Verify API key, secret, and passphrase
- Check IP restrictions
- Ensure API permissions are correct
```

**2. Rate Limit Exceeded**
```
Error: Too Many Requests
Solution:
- Reduce update frequency in PowerTraderAI+
- Check for multiple running instances
- Wait for rate limit reset (usually 1 minute)
```

**3. Connection Timeout**
```
Error: Connection timeout
Solution:
- Check internet connection
- Verify firewall settings
- Check KuCoin status page
```

**4. Invalid Symbol**
```
Error: Symbol not found
Solution:
- Use correct symbol format (BTC-USDT, not BTCUSDT)
- Check available trading pairs on KuCoin
- Verify symbol is still listed
```

### Support Resources

- **KuCoin Help Center**: [support.kucoin.com](https://support.kucoin.com)
- **API Documentation**: [docs.kucoin.com](https://docs.kucoin.com)
- **Status Page**: [status.kucoin.com](https://status.kucoin.com)
- **Community**: KuCoin Telegram/Discord groups

## Optimizing Data Quality

### Best Practices

1. **Stable Connection**: Use wired internet for reliability
2. **Backup Data Sources**: Configure alternative providers
3. **Data Validation**: Enable PowerTraderAI+'s data checking
4. **Performance Monitoring**: Track API response times

### Advanced Features

- **WebSocket Streams**: Real-time data with minimal delay
- **Historical Data**: Up to 1500 candles per request
- **Multiple Symbols**: Subscribe to multiple coins simultaneously
- **Custom Intervals**: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M

## Setup Verification

### Final Checklist

- [ ] KuCoin account created and verified
- [ ] 2FA enabled with Google Authenticator
- [ ] API keys generated with correct permissions
- [ ] IP restrictions configured (if applicable)
- [ ] API credentials securely stored
- [ ] PowerTraderAI+ successfully connects to KuCoin
- [ ] Market data is flowing correctly
- [ ] Chart updates are working

### Test Commands

Verify your setup:
```bash
# Test market data retrieval
python -c "from pt_thinker import test_kucoin_connection; test_kucoin_connection()"

# Check API status
python -c "from pt_thinker import get_server_time; print(get_server_time())"
```

## Next Steps

With KuCoin setup complete:

1. **Robinhood Setup**: [Configure trading account](robinhood-setup.md)
2. **API Integration**: [Complete API configuration](../api-configuration/README.md)
3. **Security Review**: [Implement security best practices](../security/README.md)
4. **Start Trading**: [Begin using PowerTraderAI+](../user-guide/README.md)

**Congratulations!** Your KuCoin market data feed is ready for PowerTraderAI+.
