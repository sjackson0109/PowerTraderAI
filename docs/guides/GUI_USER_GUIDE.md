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
│ • Trading: Status   │ • ETH Price Chart            │
│ • Exchange: Status  │ • Portfolio Performance      │
│ • Account Info      │ • Trade History              │
│ • Training Panel    │ • Neural Levels Overlay      │
│                     │                              │
└─────────────────────┴──────────────────────────────┘
```

### Status Indicators

#### System Status
- **Neural: running/stopped** - Neural network analysis engine
- **Trading: running/stopped** - Automated trading engine
- **Exchange: Coinbase** - In paper mode: the primary exchange, which gives the prices, candles and minimum order sizes
- **Last status: [timestamp]** - Most recent system update

#### Exchange line
The line sits on the left of the Account box, with **Trading** on the right beside its
start and stop buttons. Its colour gives the state: the accent colour when the exchange
answers, red when it does not (orange when it answers without a price), grey while
checking.

- **Paper mode** names the primary exchange: `Coinbase`.
- **Live mode** names the broker orders go to:
  - `Coinbase (live orders)`: real orders.
  - `Coinbase (preview orders)`: **Preview orders only** is ticked; nothing is bought or sold.
  - `Binance (testnet orders)`: Binance's test network.
  - `Kraken (no live orders)`, in red: this version cannot place orders on that exchange.
- `Coinbase (no prices)`, in red: no price from that exchange; click the line for the error.
- **Checking...** - Status verification in progress

### Trading Mode
**File → Trading Mode...** chooses paper or live trading and the broker:
- **Broker** lists only the exchanges this version can place orders on (Binance and Coinbase).
- **Use testnet / sandbox** is offered for Binance only.
- **Preview orders only** is offered for Coinbase and is ticked to start with. The trader then
  runs the live path, but each order is only previewed by Coinbase: nothing is bought or sold
  and nothing is recorded.
- **Check API key** shows what the saved key may do (view, trade, transfer).
- **Apply** needs **Yes, I understand real money is at risk**. It is refused when the key check
  refuses the key: a key that cannot trade is refused unless **Preview orders only** is ticked.
  A key that can transfer funds is accepted with a warning.
- Restart the trader after applying. Each live broker keeps its own trade history and
  profit-and-loss ledger.

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

Trade Start Level, the DCA settings and the profit margins are used only when **Strategy** → **Signals from** is
**Neural levels, DCA and trailing profit margin**. With a rule-based strategy (the default), the strategy decides
each buy and sale, and each buy is the **Start Allocation %**.

#### 📁 **File Paths**
- **Hub Data Directory**: Location for trade history and logs
- **Neural Runner Script**: Path to neural analysis engine
- **Trainer Script**: Path to neural network trainer
- **Trader Script**: Path to automated trader

### Strategy Settings
The **Strategy** row shows what decides each buy and sale, e.g. *Trend crossover (DEMA/TEMA) on 1-hour candles;
stops and filters: none*. **Strategy...** opens the Strategy window. Its **Save** applies at the trader's next
decision: no restart is needed. A value outside its range, or a pair of values that does not fit (a slow average no
longer than the fast one), is refused with the reason, and nothing is saved.

#### Signals from
- **Rule-based strategy** (the default): the strategy below decides each buy and sale from closed candles.
- **Neural levels, DCA and trailing profit margin**: the thinker's levels, with Trade Start Level, DCA and the
  trailing profit margin from the main Settings window.

#### Strategy
| Strategy | Buys | Sells |
|---|---|---|
| **EMA crossover** | the fast EMA crosses above the slow EMA | a candle closes with the fast EMA below the slow EMA |
| **Trend crossover (DEMA/TEMA)** (the default) | the fast average crosses above the slow one and stays above for the confirmation candles; with the ADX filter on, ADX is at least the minimum | a candle closes with the fast average below the slow one |
| **Supertrend** | the trend turns up and stays up for the confirmation candles | a candle closes below the Supertrend line |

Each parameter shows its range and default, with a description under it. **Reset to defaults** puts back the
selected strategy's defaults. Each strategy keeps its own values.

#### Candles
The strategy decides once each candle closes: on 1-hour candles, once an hour for each coin, shortly after the
hour. Prices, values and the Current Trades table still update live. The chart's own timeframe only changes the
chart. Choices: 1, 3, 5, 15 and 30 minutes; 1, 2, 4, 6, 8 and 12 hours; 1 day.

#### Stops and filters
Tick any of them. Stops are checked when each candle closes: a candle that closes below the stop sells the coin at
the market price. With more than one stop ticked, the highest one applies, and a stop never moves down.
- **Ratchet stop**: from the start gain, a stop at the first stop % above the buy price, raised one step for each
  further step of gain.
- **ATR trailing stop**: the highest close since the buy, minus a multiple of the ATR.
- **Profit lock stages**: stages of gain %:lock %, e.g. `3:1, 6:3, 10:6`.
- **Pause after a sale**: no new buy in the coin (or in every coin) for a number of candles after a sale, and for
  longer after a sale at a loss.

### Exchange Provider Settings

#### Region
**Options**: US, EU or Global. The region is saved with your exchange settings. It does not change which exchanges you can choose: check that an exchange serves your country before you use it.

#### Primary Exchange
**Purpose**: The exchange PowerTrader reads prices, candles and minimum order sizes from first. When it has no answer, the other exchanges enabled in **Configure Exchange APIs** are asked, in order.

**How it works**:
- The list shows every exchange this version reads prices from: Binance, Coinbase, Kraken and KuCoin.
- A new install uses Coinbase, with Kraken, KuCoin and Binance enabled as fallbacks. Your choice replaces this.
- Your choice is never changed for you. Saving Settings also enables the exchange you chose.
- Your primary exchange cannot be disabled in **Configure Exchange APIs**. Choose another primary first.
- If your primary exchange cannot connect, the other enabled exchanges answer in order. None of them takes its place as primary, and the hub's Exchange status shows the error.
- Live orders go to the broker chosen in **Trading Mode**, not to the primary exchange.

#### Advanced Exchange Options
- **🔍 Price Comparison Enabled**: Compare prices across multiple exchanges before trading
- **Auto Best Price**: Automatically route orders to exchange with best prices
- **Exchange Setup**: Launch credential configuration wizard

### Paper Trading Settings

#### Paper-trading coins
**Purpose**: The coins paper trading opens new trades in.

- **Inherit coins from main settings** (the default): every coin in **Coins**.
- **Override paper-trading coins**: only the coins you tick. There is one tick box for each coin in **Coins**. The first time you override, every coin starts ticked; once an override is saved, a coin added to **Coins** starts unticked. At least one coin must be ticked.
- A position already held is still sold by its exit rules after its coin is unticked.
- Live trading always uses every coin in **Coins**.

#### Paper Account
**Paper Account...** sets the starting balance, the cash and the positions the paper trader starts from.

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

#### Requests per second
Each exchange limits how many requests it takes from one internet address. PowerTrader keeps every request it
sends to an exchange (prices, candles, orders) within that limit, counting every PowerTrader window and process on
your computer together, because they share your address.

| Exchange | Published limit used |
|---|---|
| Coinbase | 10 a second |
| Kraken | 1 a second |
| KuCoin | 66 a second (2,000 per 30 seconds) |
| Binance | 10 a second (6,000 request weight a minute) |
| any other | 5 a second (PowerTrader's default) |

**Setup Exchange** shows the figure for the exchange you select. Type another figure and press **Save limit** to use
it instead, or **Use published limit** to go back. No API key is needed for this.

#### Candles kept on your computer
Candles are saved per exchange in PowerTrader's cache folder. Only bars that are not there yet are asked
for. Sizes an exchange does not serve itself (Coinbase has no 2-, 4-, 8- or 12-hour or weekly candles) are built from
the smaller bars already saved. When an exchange has no bars before a coin's first one (a coin listed later), that is
saved too, and the months before the listing are not asked for again for 30 days.

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
   - Trading: running ✅
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
- **Trading: stopped** → Exchange issues or insufficient funds
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
