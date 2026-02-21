# Gemini Exchange Setup Guide

Complete setup instructions for integrating Gemini with PowerTraderAI+ multi-exchange system.

## 🌍 About Gemini

Gemini is a regulated cryptocurrency exchange founded by the Winklevoss twins. Known for its strong regulatory compliance and institutional-grade security, Gemini serves both retail and institutional customers with a focus on trust and transparency.

### Key Features
- **Regulatory Compliance**: New York Trust Company charter
- **Institutional Grade**: Custody and prime brokerage services
- **Insurance Coverage**: FDIC insurance for USD deposits
- **Security Focus**: SOC 2 Type 2 certified operations
- **Winklevoss Leadership**: Founded by Cameron and Tyler Winklevoss

## 🔑 API Configuration

### Step 1: Create API Credentials

1. **Log into Gemini**: Visit [exchange.gemini.com](https://exchange.gemini.com) and sign in
2. **Navigate to API Settings**:
   ```
   Account → Settings → API Keys → Create a New API Key
   ```

3. **Configure API Permissions**:
   - ✅ **Fund Management**: View account balances
   - ✅ **Trading**: Place and cancel orders
   - ✅ **Order History**: View trading history
   - ❌ **Transfer Funds**: Keep disabled for security

4. **Security Options**:
   - **Session Length**: Set appropriate duration
   - **IP Restrictions**: Add your server's IP address
   - **Require Heartbeat**: Enable for active sessions

5. **Save Credentials**:
   - **API Key**: Copy the public key
   - **API Secret**: Copy the private key (shown only once)

### Step 2: Configure in PowerTraderAI+

#### GUI Method:
1. **Open Exchange Settings**: Settings → Exchanges → Gemini
2. **Enter Credentials**:
   ```
   API Key: your_gemini_api_key
   API Secret: your_gemini_api_secret
   Sandbox: false (for live trading)
   ```

3. **Test Connection**: Click "Test API" button

#### Configuration File Method:
```json
{
  "gemini": {
    "api_key": "your_gemini_api_key",
    "api_secret": "your_gemini_api_secret",
    "sandbox": false,
    "base_url": "https://api.gemini.com"
  }
}
```

#### Environment Variables:
```bash
export POWERTRADER_GEMINI_API_KEY="your_api_key"
export POWERTRADER_GEMINI_API_SECRET="your_secret_key"
```

## 📊 Trading Features

### Supported Trading Pairs
Gemini offers carefully curated trading pairs:
- **Major pairs**: BTC/USD, ETH/USD, LTC/USD
- **Popular alts**: BCH/USD, LINK/USD, ZEC/USD
- **Stablecoins**: GUSD/USD, USDC/USD, DAI/USD
- **DeFi tokens**: UNI/USD, COMP/USD, AAVE/USD
- **Cross pairs**: BTC/ETH, ETH/DAI

### Order Types
- **Market Orders**: Immediate execution at current price
- **Limit Orders**: Execute at specified price or better
- **Immediate-or-Cancel (IOC)**: Fill immediately or cancel
- **Fill-or-Kill (FOK)**: Complete fill or cancel entirely
- **Auction-Only**: Participate in daily auctions only
- **Indication-of-Interest**: Large block trading

### Trading Modes
- **Individual Account**: Personal trading account
- **Institution Account**: Corporate and fund accounts
- **Custody Account**: Institutional custody services
- **Prime Brokerage**: Professional trading services

## 🌐 Regional Availability

### Supported Regions
- ✅ **United States**: All 50 states (with some restrictions)
- ✅ **Canada**: Full service availability
- ✅ **United Kingdom**: FCA regulated operations
- ✅ **Singapore**: Digital payment token license
- ✅ **South Korea**: Virtual asset business registration

### Regulatory Compliance
- **New York Trust Company**: State-chartered trust company
- **NYDFS Regulated**: New York Department of Financial Services
- **FCA Authorized**: UK Financial Conduct Authority
- **SOC 2 Type 2**: Security and availability certification
- **FDIC Insurance**: USD deposits insured up to $250K

## 💰 Fees Structure

### Trading Fees
| 30-Day Volume | Fee Rate | Maker Rebate |
|---------------|----------|--------------|
| $0 - $10K | 1.00% | 0.00% |
| $10K - $50K | 0.75% | 0.00% |
| $50K - $100K | 0.50% | 0.00% |
| $100K - $250K | 0.35% | 0.00% |
| $250K - $500K | 0.25% | 0.00% |
| $500K - $1M | 0.20% | 0.00% |
| $1M - $2.5M | 0.15% | 0.00% |
| $2.5M - $5M | 0.10% | 0.00% |
| $5M+ | 0.10% | 0.05% |

### Additional Fees
- **ACH Deposits**: Free
- **Wire Deposits**: Free
- **Cryptocurrency Deposits**: Free
- **ACH Withdrawals**: Free
- **Wire Withdrawals**: $30 fee
- **Cryptocurrency Withdrawals**: Network fees only

### Institutional Pricing
- **Prime Brokerage**: Custom pricing for institutions
- **OTC Trading**: Competitive rates for large blocks
- **Custody Services**: Asset-based fee structure
- **API Trading**: No additional API fees

## ⚙️ PowerTraderAI+ Integration

### Automated Trading
```python
from pt_multi_exchange import MultiExchangeManager

# Initialize with Gemini
manager = MultiExchangeManager()
gemini_data = await manager.get_market_data("BTC-USD", "gemini")

print(f"Gemini BTC price: ${gemini_data.price}")
```

### Institutional Features
Gemini's professional features work well with PowerTraderAI+:
- **Large Order Management**: Efficient execution of large trades
- **Custody Integration**: Secure asset storage
- **Regulatory Compliance**: Automated compliance reporting
- **Risk Management**: Professional risk controls

### API Advantages
PowerTraderAI+ can leverage Gemini's robust API:
- **Rate Limiting**: Generous API rate limits
- **Order Management**: Advanced order placement
- **Market Data**: High-quality price feeds
- **Account Management**: Comprehensive account data

## 🛡️ Security Features

### Account Security
- **2FA Required**: Mandatory two-factor authentication
- **Device Authorization**: Whitelist trusted devices
- **Email Notifications**: All account activity alerts
- **Address Whitelisting**: Pre-approved withdrawal addresses

### Technical Security
- **Cold Storage**: 95% of funds stored offline
- **Multi-Signature**: Enhanced wallet security
- **Hardware Security Modules**: Cryptographic key protection
- **Air-Gapped Systems**: Offline transaction signing

### Regulatory Security
- **Segregated Funds**: Customer funds held separately
- **FDIC Insurance**: USD deposits insured
- **SOC 2 Compliance**: Audited security controls
- **Regular Examinations**: Regulatory oversight

### Operational Security
- **24/7 Monitoring**: Continuous security monitoring
- **Incident Response**: Dedicated security team
- **Bug Bounty**: Ongoing security research program
- **Penetration Testing**: Regular security assessments

## 🚨 Troubleshooting

### Common Issues

#### Account Verification
```
Error: "Account not verified for trading"
```
**Solution**:
- Complete identity verification
- Provide required documentation
- Wait for verification (24-48 hours)
- Contact support if needed

#### API Access
```
Error: "API key not authorized"
```
**Solution**:
- Verify API key permissions
- Check IP address restrictions
- Ensure heartbeat if enabled
- Generate new API key if needed

#### Trading Restrictions
```
Error: "Insufficient funds for trade"
```
**Solution**:
- Check available trading balance
- Account for trading fees
- Verify order parameters
- Consider minimum order sizes

### API Limits
- **REST API**: 120 requests per minute
- **WebSocket**: Real-time data with no limits
- **Order Rate**: 5 orders per second
- **Market Data**: No restrictions on public endpoints

### Debug Mode
Enable detailed logging:
```python
import logging
logging.getLogger('gemini').setLevel(logging.DEBUG)
```

## 📈 Advanced Features

### Gemini Custody
Institutional-grade custody services:
- **Segregated Storage**: Individually segregated accounts
- **Insurance Coverage**: Comprehensive digital asset insurance
- **Compliance**: SOC 2 Type 2 audited operations
- **Access Controls**: Multi-approval transaction workflows

### Gemini Dollar (GUSD)
Regulated stablecoin offering:
- **Dollar-Backed**: 1:1 USD collateralization
- **NYDFS Approved**: Regulatory oversight
- **Monthly Attestations**: Public reserve reports
- **ERC-20 Compatible**: Ethereum blockchain integration

### ActiveTrader Platform
Professional trading interface:
- **Advanced Charts**: TradingView integration
- **Order Book**: Full market depth display
- **Order Types**: Professional order management
- **Portfolio Analytics**: Comprehensive portfolio tools

### API Trading
Comprehensive API features:
- **REST API**: Complete trading functionality
- **WebSocket**: Real-time market data
- **FIX API**: Professional trading protocol
- **Market Data**: Historical and real-time data

## 🔗 Resources

### Documentation & Support
- **Gemini Support**: support.gemini.com
- **API Documentation**: docs.gemini.com
- **Status Page**: status.gemini.com
- **Security**: gemini.com/security

### Educational Resources
- **Gemini Cryptopedia**: Educational content library
- **Blog**: Market insights and updates
- **Research**: Market analysis reports
- **Webinars**: Educational sessions

### Professional Services
- **Custody**: Institutional custody solutions
- **Prime Brokerage**: Professional trading services
- **OTC Trading**: Large block execution
- **Clearing**: Trade settlement services

### Developer Tools
- **Sandbox Environment**: Testing and development
- **API Libraries**: Multiple programming languages
- **WebSocket Feeds**: Real-time data streams
- **Documentation**: Comprehensive API docs

---

**Next Steps**: With Gemini configured, you now have access to a highly regulated and secure exchange platform. Use PowerTraderAI+'s institutional features to leverage Gemini's professional-grade infrastructure and regulatory compliance for secure, compliant trading operations.
