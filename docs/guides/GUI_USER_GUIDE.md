# PowerTraderAI+ - Desktop GUI User Guide

## Overview

The PowerTraderAI+ desktop application (`pt_hub.py`) provides a comprehensive graphical interface for managing your cryptocurrency trading operations with multi-exchange support.

## Main Interface

### Layout Overview
```
┌─────────────────────┬──────────────────────────────┐
│ Controls/Health     │ Price Charts & Analysis      │
│                     │                              │
│ • Neural: Status    │ • BTC Price Chart            │
│ • Trader: Status    │ • ETH Price Chart            │
│ • Exchange: Status  │ • Portfolio Performance      │
│ • Account Info      │ • Trade History              │
│ • Training Panel    │ • Neural Levels Overlay      │
│                     │                              │
└─────────────────────┴──────────────────────────────┘
```

### Status Indicators

#### System Status
- **Neural: running/stopped** - Neural network analysis engine
- **Trader: running/stopped** - Automated trading engine
- **Exchange: Connected KRAKEN** - Primary exchange connection status
- **Last status: [timestamp]** - Most recent system update

#### Exchange Status Icons
- **Connected EXCHANGE_NAME** - Connected and operational
- **Limited EXCHANGE_NAME** - Connected but limited functionality
- **Failed EXCHANGE_NAME** - Connection failed or unavailable
- **Checking...** - Status verification in progress

### Control Buttons
- **Start All** - Launch neural analysis and trading systems
- **Stop All** - Safely shutdown all trading operations
- **Train Selected** - Train neural network for selected cryptocurrency
- **Train All** - Train neural networks for all configured cryptocurrencies

## Settings Configuration

### Opening Settings
**Menu Bar** → **Settings** → **Open Settings Dialog**

### Core Trading Settings

#### **Trading Configuration**
- **Main Neural Directory**: Location of neural network models
- **Coins**: Comma-separated list of cryptocurrencies to trade
- **Trade Start Level**: Neural confidence level required to start trades (1-7)
- **Start Allocation %**: Initial percentage of portfolio per trade
- **DCA Multiplier**: Dollar-cost averaging multiplier for additional buys
- **DCA Levels**: Price drop percentages for additional purchases
- **Max DCA Buys**: Maximum DCA purchases per 24 hours

#### **Profit Management**
- **Profit Margin (No DCA)**: Target profit percentage without DCA
- **Profit Margin (With DCA)**: Target profit percentage when using DCA
- **Trailing Gap**: Percentage gap for trailing stop losses

#### 📁 **File Paths**
- **Hub Data Directory**: Location for trade history and logs
- **Neural Runner Script**: Path to neural analysis engine
- **Trainer Script**: Path to neural network trainer
- **Trader Script**: Path to automated trader

### Exchange Provider Settings

#### Regional Selection
**Purpose**: Determines which exchanges are available based on regulatory compliance

**Options**:
- **🇺🇸 US** - United States regulated exchanges only
- **🇪🇺 EU/UK** - European Union and UK compliant exchanges
- **🌐 Global** - All supported exchanges worldwide

**Available Exchanges by Region**:

| Region | Available Exchanges |
|--------|-------------------|
| 🇺🇸 US | Robinhood, Coinbase, Kraken, Binance.US, KuCoin |
| 🇪🇺 EU/UK | Kraken, Coinbase, Binance, Bitstamp, KuCoin |
| 🌐 Global | Binance, Kraken, KuCoin, Coinbase, Bybit, OKX |

#### Primary Exchange Selection
**Purpose**: Your main trading exchange for order execution

**How it works**:
1. Select your region first
2. Dropdown automatically filters to compliant exchanges
3. Choose your preferred exchange
4. System validates availability and credentials

#### Advanced Exchange Options
- **🔍 Price Comparison Enabled**: Compare prices across multiple exchanges before trading
- **Auto Best Price**: Automatically route orders to exchange with best prices
- **Exchange Setup**: Launch credential configuration wizard

### Performance Settings

#### UI Refresh Settings
- **UI Refresh Seconds**: How often the interface updates (default: 2.0)
- **Chart Refresh Seconds**: How often price charts update (default: 10.0)
- **Candles Limit**: Maximum number of price bars to display (default: 500)

#### Startup Options
- **Auto Start Scripts**: Automatically start trading systems when app launches

## Exchange Setup Wizard

### Accessing the Setup Wizard
1. **Settings Dialog** → **Exchange Provider Settings**
2. Click **🔧 Exchange Setup** button
3. Follow interactive prompts

### Setup Process

#### 1. Exchange Selection
```
Available exchanges for your region:
1. Robinhood (Commission-free)
2. Coinbase (Beginner-friendly)
3. Kraken (Professional)
4. Binance (High liquidity)
5. KuCoin (Wide selection)

Select exchange number: 3
```

#### 2. Credential Configuration
**For API-based exchanges (Kraken, Binance, etc.)**:
```
Enter Kraken API Key: your_api_key_here
Enter Kraken API Secret: your_secret_here
Test connection? (y/n): y
✅ Connection successful!
```

**For login-based exchanges (Robinhood)**:
```
Enter username: your_username
Enter password: your_password
Enable 2FA device ID? (optional): device_id
Test connection? (y/n): y
✅ Authentication successful!
```

#### 3. Verification
- **Connection Test**: Verifies API credentials
- **Market Data Test**: Confirms price feed access
- **Balance Check**: Validates account access
- **Trading Permissions**: Checks order placement capabilities

## 📈 Trading Operations

### Starting Trading Systems

#### Prerequisites
1. **✅ Exchanges Configured**: At least one exchange set up with credentials
2. **✅ Neural Models Trained**: Complete training for your selected cryptocurrencies
3. **✅ Account Funded**: Sufficient balance for trading operations

#### Training Neural Networks
1. **Select cryptocurrency** from "Train coin" dropdown
2. Click **Train Selected** for single coin
3. Or click **Train All** for all configured cryptocurrencies
4. **Wait for completion** - status shows in training panel
5. **Verify readiness** - "Training: READY (all trained)" appears

#### Starting Operations
1. **Ensure all training complete** - "Start All" button becomes enabled
2. Click **Start All** to begin operations
3. **Monitor status indicators**:
   - Neural: running ✅
   - Trader: running ✅
   - Exchange: ✅ CONNECTED
4. **View real-time data** in charts and trade history

### Monitoring Active Trading

#### Real-Time Information
- **Account Value Chart**: Portfolio performance over time
- **Individual Coin Charts**: Price movements with neural level overlays
- **Trade History Table**: Recent buy/sell transactions
- **Current Positions**: Open trades and profit/loss status
- **Neural Levels**: Visual indicators of AI confidence levels

#### Key Metrics Dashboard
- **Total Account Value**: Current portfolio worth
- **Holdings Value**: Value of cryptocurrency positions
- **Buying Power**: Available cash for new trades
- **Percent In Trade**: Portion of portfolio actively trading
- **Realized Profit**: Completed trade profits/losses

## 🚨 Error Handling & Troubleshooting

### Common Status Messages

#### Exchange Status Issues
- **❌ Connection failed** → Check internet, exchange API status, credentials
- **⚠️ Limited functionality** → Some features unavailable, trading may be restricted
- **Checking...** → Initial connection attempt, wait for completion
- **❌ Authentication failed** → Verify API keys, check permissions

#### Trading System Issues
- **Neural: stopped** → Training incomplete or system error
- **Trader: stopped** → Exchange issues or insufficient funds
- **Training: REQUIRED** → Must train neural networks before trading
- **Flow: Train All required** → Complete training before starting operations

### Recovery Actions

#### For Exchange Problems
1. **Check Settings** → Verify region and exchange selection
2. **Test Credentials** → Run Exchange Setup wizard
3. **Try Alternative Exchange** → Switch to backup exchange
4. **Check Exchange Status** → Visit exchange website for maintenance

#### For Trading Problems
1. **Stop All Operations** → Click "Stop All" button
2. **Review Logs** → Check error messages in interface
3. **Retrain Networks** → Click "Train All" if models corrupted
4. **Restart Application** → Close and reopen pt_hub.py

#### For Performance Issues
1. **Adjust Refresh Rates** → Increase refresh intervals in settings
2. **Reduce Candle Limit** → Lower number of chart bars
3. **Close Unused Charts** → Remove extra cryptocurrency tabs
4. **Check System Resources** → Monitor CPU and memory usage

## 🔧 Advanced Configuration

### Custom Neural Network Settings
Edit neural network parameters in individual coin directories:
```
main_neural_dir/
├── BTC/
│   ├── neural_trainer.py
│   └── config.json
├── ETH/
│   ├── neural_trainer.py
│   └── config.json
```

### Multi-Exchange Price Optimization
Enable advanced features in settings:
- **Price Comparison**: See prices across all configured exchanges
- **Auto Best Price**: System automatically chooses best execution
- **Smart Order Routing**: Splits large orders across multiple exchanges

### Custom Trading Strategies
Modify trading parameters per cryptocurrency:
- **Individual DCA Levels**: Different strategies per coin
- **Coin-Specific Allocation**: Varying portfolio percentages
- **Custom Profit Targets**: Individual profit margins

## 📱 Integration & Extensions

### External Monitoring
Connect external tools to PowerTrader data. The files are in `hub_data/<mode>/` inside the
data folder (`%LOCALAPPDATA%\SJackson\PowerTraderAI\` on Windows, see
[Where your data lives](../../README.md#where-your-data-lives)); `<mode>` is `paper`,
`testnet`, or empty for live:
```
hub_data/paper/
├── trader_status.json      # Current trading status
├── trade_history.jsonl     # Complete trade log
├── account_value_history.jsonl  # Portfolio performance
└── pnl_ledger.json        # Profit/loss summary
```

### API Access
Programmatic access to trading data:
```python
import json
import os
import sys

sys.path.insert(0, "app")
import pt_paths  # resolves the data folder for this machine

hub = os.path.join(pt_paths.hub_dir(), "paper")

# Read current status
with open(os.path.join(hub, 'trader_status.json')) as f:
    status = json.load(f)
    print(f"Active positions: {len(status.get('positions', []))}")

# Monitor account value
with open(os.path.join(hub, 'account_value_history.jsonl')) as f:
    for line in f:
        data = json.loads(line)
        print(f"{data['timestamp']}: ${data['total_value']}")
```

### Custom Notifications
Set up alerts for trading events:
- **Large Profit/Loss**: Configure thresholds for notifications
- **Exchange Disconnections**: Immediate alerts for connection issues
- **Training Completion**: Notifications when neural networks finish training
- **Order Execution**: Confirmations for buy/sell transactions

## 🛡️ Security Best Practices

### Credential Management
- **Secure Storage**: Credentials encrypted in `credentials/` directory
- **File Permissions**: Restrict access to credential files (chmod 600)
- **Regular Rotation**: Update API keys periodically
- **Backup Credentials**: Store securely offline

### Trading Safety
- **Start Small**: Begin with minimal allocations for testing
- **Monitor Actively**: Don't leave system unattended initially
- **Set Limits**: Configure maximum trade sizes and DCA limits
- **Regular Backups**: Save neural network models and configurations

### System Security
- **Updated Software**: Keep PowerTrader and dependencies current
- **Secure Environment**: Use dedicated trading computer/VM
- **Network Security**: Secure internet connection, consider VPN
- **Access Control**: Limit who can access trading systems

---

**PowerTraderAI+ Desktop GUI** - Your comprehensive cryptocurrency trading command center.
