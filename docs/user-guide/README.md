# PowerTraderAI+ User Guide

Learn how to use PowerTraderAI+ for automated cryptocurrency trading with AI-powered price predictions.

## Overview

PowerTraderAI+ is an advanced cryptocurrency trading bot that combines:
- **AI Price Prediction**: Machine learning models for market forecasting
- **Automated Trading**: Dollar-cost averaging (DCA) strategies
- **Risk Management**: Comprehensive safety and security features
- **Real-time Monitoring**: Live charts and performance tracking

## Main Interface

### Application Layout

```
┌─────────────────────────────────────────────────────────┐
│ PowerTraderAI+                                   [_][□][×]│
├─────────────────────────────────────────────────────────┤
│ File  Settings  Tools  Help                             │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│ │   Market    │ │  Trading    │ │   AI/ML     │        │
│ │    Data     │ │   Status    │ │ Predictions │        │
│ └─────────────┘ └─────────────┘ └─────────────┘        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│                 Live Chart Area                         │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ Status: Ready | Balance: $X.XX | Last Update: XX:XX    │
└─────────────────────────────────────────────────────────┘
```

### Key Components

1. **Menu Bar**: Access to settings, tools, and help
2. **Information Panels**: Market data, trading status, AI predictions
3. **Live Chart**: Real-time price charts with technical indicators
4. **Status Bar**: Current application status and key metrics

## Getting Started

### First Launch

1. **Start Application**:
   ```bash
   python pt_hub.py
   ```

2. **Setup Wizard**: Complete initial configuration
   - Exchange API setup
   - Trading parameters
   - Security settings

3. **Verify Connections**: Ensure all services are connected

### Initial Configuration

#### Trading Parameters

- **Portfolio Balance**: Starting capital amount
- **Risk Level**: Conservative, Moderate, or Aggressive
- **DCA Settings**: Investment frequency and amounts
- **Stop Loss**: Maximum acceptable loss percentage

#### AI Model Settings

- **Prediction Window**: 1-hour to 24-hour forecasts
- **Model Confidence**: Minimum confidence threshold
- **Training Data**: Historical data period for learning

## Using the Charts

### Chart Features

- **Real-time Updates**: Live price data from KuCoin
- **Multiple Timeframes**: 1m, 5m, 15m, 1h, 4h, 1d
- **Technical Indicators**: Moving averages, RSI, MACD
- **Volume Analysis**: Trading volume overlays
- **AI Predictions**: Forecasted price movements

### Chart Controls

- **Zoom**: Mouse wheel or zoom buttons
- **Pan**: Click and drag to move view
- **Timeframe**: Select from dropdown menu
- **Indicators**: Toggle technical analysis tools

### Interpreting the Display

```
Price Chart Elements:
├── Candlesticks: OHLC price data
├── Volume Bars: Trading volume
├── Moving Averages: Trend indicators
├── Support/Resistance: Key price levels
└── AI Predictions: Forecasted movements
```

## 🤖 AI Trading Features

### Price Prediction

The AI system analyzes:
- **Historical Price Data**: Past price movements and patterns
- **Volume Analysis**: Trading activity and liquidity
- **Technical Indicators**: RSI, MACD, Bollinger Bands
- **Market Sentiment**: News and social media indicators

### Prediction Accuracy

- **Confidence Scores**: 0-100% prediction reliability
- **Time Windows**: Short-term (1-4h) and medium-term (1-7d)
- **Success Rate**: Historical prediction accuracy tracking

### Automated Trading

#### DCA Strategy

Dollar-Cost Averaging implementation:
- **Regular Intervals**: Scheduled purchases (daily, weekly, monthly)
- **Smart Timing**: AI-optimized entry points
- **Risk Management**: Automatic position sizing
- **Market Conditions**: Adjustment based on volatility

#### Trade Execution

1. **Signal Generation**: AI identifies trading opportunities
2. **Risk Assessment**: Position size and stop-loss calculation
3. **Order Placement**: Automatic trade execution via Robinhood
4. **Monitoring**: Continuous position tracking

## Settings and Configuration

### Accessing Settings

- **Menu**: Settings → Preferences
- **Keyboard**: `Ctrl + ,`
- **Right-click**: Context menu on main interface

### Key Settings Categories

#### Trading Settings

- **Default Coin**: Primary cryptocurrency to trade
- **Portfolio Allocation**: Percentage distribution
- **Risk Parameters**: Maximum loss, position size
- **Trading Hours**: Active trading schedule

#### AI/ML Settings

- **Model Selection**: Choose prediction algorithms
- **Training Period**: Historical data window
- **Confidence Threshold**: Minimum prediction confidence
- **Update Frequency**: Model retraining schedule

#### Display Settings

- **Theme**: Light or dark mode
- **Chart Refresh**: Update frequency (seconds)
- **Time Zone**: Local time display
- **Notifications**: Alert preferences

### Configuration Files

PowerTraderAI+ stores settings in:
- `gui_settings.json`: User interface preferences
- `trading_config.json`: Trading parameters
- `ai_config.json`: AI model settings

## Monitoring Performance

### Performance Metrics

Track your trading success with:
- **Total Return**: Overall portfolio performance
- **Win Rate**: Percentage of profitable trades
- **Average Trade**: Mean profit/loss per trade
- **Sharpe Ratio**: Risk-adjusted returns

### Real-time Monitoring

- **Live P&L**: Current profit/loss status
- **Active Positions**: Open trades and their status
- **Recent Trades**: Trade history and outcomes
- **Market Data**: Current price and volume

### Reports and Analytics

Generate detailed reports:
- **Daily Performance**: Day-by-day results
- **Monthly Summary**: Comprehensive monthly analysis
- **AI Accuracy**: Prediction success tracking
- **Risk Analysis**: Drawdown and volatility metrics

## Tools and Utilities

### Built-in Tools

1. **Paper Trading**: Test strategies without real money
2. **Backtesting**: Test on historical data
3. **Risk Calculator**: Position sizing and stop-loss tools
4. **Market Scanner**: Find trading opportunities

### External Integrations

- **KuCoin**: Real-time market data
- **Robinhood**: Trade execution and portfolio
- **News APIs**: Market sentiment analysis
- **Social Media**: Sentiment tracking

## Safety Features

### Risk Management

- **Stop Loss Orders**: Automatic loss limitation
- **Position Limits**: Maximum investment per trade
- **Daily Loss Limits**: Maximum daily drawdown
- **Margin Requirements**: Leverage restrictions

### Security Measures

- **API Key Encryption**: Secure credential storage
- **Session Timeouts**: Automatic security logouts
- **Audit Logging**: Complete trade history
- **Backup Systems**: Data protection and recovery

## Emergency Procedures

### Emergency Stop

**Immediate halt of all trading**:
1. Click "Emergency Stop" button (red)
2. Or press `Ctrl + Alt + S`
3. Confirm shutdown in dialog box

### Manual Override

**Take manual control**:
- Disable AI trading: Settings → AI → Disable
- Switch to manual mode: Trading → Manual Mode
- Close positions: Trading → Close All Positions

### System Recovery

**If application crashes**:
1. Restart application: `python pt_hub.py`
2. Check log files in `logs/` directory
3. Verify position status via Robinhood
4. Contact support if needed

## Support and Help

### Getting Help

- **Built-in Help**: Press `F1` or Help → Documentation
- **Error Messages**: Check status bar and logs
- **GitHub Issues**: Report bugs and request features
- **Community**: Discord server for user support

### Troubleshooting

Common issues and solutions:
- **Connection Problems**: Check internet and API status
- **Trade Failures**: Verify account balance and permissions
- **Performance Issues**: Monitor system resources
- **Data Issues**: Clear cache and restart

### Log Files

Monitor application health:
- `logs/powertrader.log`: General application logs
- `logs/trading.log`: Trade execution logs
- `logs/ai.log`: AI model logs
- `logs/error.log`: Error and exception logs

## Next Steps

- [Exchange Setup](../exchanges/README.md): Configure KuCoin and Robinhood
- [API Configuration](../api-configuration/README.md): Set up API keys
- [Security Guide](../security/README.md): Secure your trading setup
- [Troubleshooting](../troubleshooting/README.md): Solve common issues