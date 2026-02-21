# PowerTraderAI+ Desktop Installation Guide

**Version 4.0.0** | **Windows Desktop Application**

## Overview

PowerTraderAI+ is a sophisticated desktop trading application with advanced paper trading, live monitoring, risk management, and cost analysis capabilities. This guide provides complete installation and configuration instructions for the Windows desktop version.

## System Requirements

### Minimum Requirements
- **Operating System:** Windows 10 (64-bit) or Windows 11
- **RAM:** 4 GB minimum, 8 GB recommended
- **Storage:** 500 MB for application + 1 GB for data
- **Python:** Python 3.9 or higher (required)
- **Internet:** Broadband connection for data feeds and updates

### Recommended Requirements
- **Operating System:** Windows 11 (latest updates)
- **RAM:** 16 GB for optimal performance
- **Storage:** SSD with 2 GB+ available space
- **Python:** Python 3.11 with pip and virtual environment support
- **Display:** 1920x1080 resolution or higher

## Pre-Installation Setup

### 1. Install Python
1. Download Python from [python.org/downloads/](https://python.org/downloads/)
2. **IMPORTANT:** During installation, check "Add Python to PATH"
3. Verify installation:
   ```cmd
   python --version
   pip --version
   ```

### 2. Install Required System Packages
Open Command Prompt as Administrator and run:
```cmd
python -m pip install --upgrade pip
```

## Installation Process

### Step 1: Download and Extract
1. Download the latest PowerTraderAI+ Desktop release from GitHub Releases
2. Extract the ZIP file to a temporary directory (e.g., `C:\Temp\PowerTraderInstaller`)
3. Navigate to the extracted directory

### Step 2: Run Installer
1. Right-click `install.bat` and select "Run as Administrator"
2. Follow the installation prompts
3. Wait for the installation to complete

**Installation Locations:**
- Application: `%USERPROFILE%\PowerTraderAI+\`
- Configuration: `%USERPROFILE%\PowerTraderAI+\config\`
- Data: `%USERPROFILE%\PowerTraderAI+\data\`
- Logs: `%USERPROFILE%\PowerTraderAI+\logs\`

### Step 3: Setup Python Environment
1. Double-click the "PowerTraderAI+ Setup" shortcut on your desktop
2. Wait for Python packages to install automatically
3. Close the setup window when complete

### Step 4: Launch Application
1. Double-click the "PowerTraderAI+" shortcut on your desktop
2. The application will initialize and open the main interface
3. First-time setup wizard will guide you through initial configuration

## Application Features

### Main Interface Components

#### 1. Trading Control Panel
- **Paper Trading Account:** Virtual trading with realistic market simulation
- **Quick Trade Controls:** Direct buy/sell with customizable quantities
- **Account Status:** Real-time portfolio valuation and P&L tracking
- **Position Management:** Active position monitoring with unrealized gains/losses

#### 2. Risk Management
- **Position Limits:** Configurable maximum position sizes
- **Loss Controls:** Daily loss limits and stop-loss automation
- **Risk Scenarios:** Pre-configured conservative, moderate, and aggressive settings
- **Real-time Monitoring:** Continuous risk assessment and alerts

#### 3. Live Monitoring
- **Market Data:** Real-time price feeds for monitored assets
- **Alert System:** Customizable price, volume, and volatility alerts
- **Performance Tracking:** Historical performance analysis and reporting
- **Integration Status:** System health and connectivity monitoring

#### 4. Cost Analysis
- **Performance Tiers:** Budget, Professional, and Enterprise cost models
- **Monthly Projections:** Detailed cost breakdowns by category
- **Efficiency Metrics:** Cost per dollar managed and break-even analysis
- **Scenario Planning:** Compare different trading volume scenarios

## Configuration

### Initial Setup Wizard

The first time you launch PowerTraderAI+, you'll be guided through:

1. **Account Setup**
   - Select trading mode (Paper Trading recommended for new users)
   - Configure initial virtual balance
   - Set up basic risk parameters

2. **Asset Selection**
   - Choose cryptocurrencies to monitor (BTC, ETH, ADA, DOT, MATIC)
   - Configure refresh intervals
   - Set up alert preferences

3. **Risk Settings**
   - Maximum position size per trade
   - Daily loss limits
   - Auto-stop-loss parameters

### Advanced Configuration

#### Settings File: `config/settings.json`
```json
{
  "coins": ["BTC", "ETH", "ADA", "DOT", "MATIC"],
  "auto_start_scripts": false,
  "main_neural_dir": "./neural_data",
  "hub_data_dir": "./hub_data",
  "paper_trading": {
    "initial_balance": 10000.00,
    "commission_rate": 0.001
  },
  "risk_management": {
    "max_position_size_pct": 20,
    "max_daily_loss_pct": 5,
    "risk_per_trade_pct": 2
  },
  "monitoring": {
    "refresh_interval_seconds": 10,
    "alert_levels": ["WARNING", "ERROR", "CRITICAL"]
  }
}
```

#### Logging Configuration: `config/logging_config.json`
- Adjustable log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- File rotation settings (10 MB files, 5 backup copies)
- Console and file output configuration

## User Guide

### Paper Trading Workflow

1. **Initialize Account**
   - Open Trading Control Panel
   - Select "Paper Trading" mode
   - Set initial balance (default: $10,000)
   - Click "Initialize Account"

2. **Enable Trading**
   - Click "Enable Trading" button
   - Trading controls become active
   - Start with small test trades

3. **Execute Trades**
   - Enter symbol (e.g., "BTC")
   - Set quantity (e.g., "0.01")
   - Click Buy or Sell
   - Monitor results in Account Status

4. **Monitor Performance**
   - Real-time P&L updates every 10 seconds
   - Position tracking with unrealized gains/losses
   - Win rate and trade statistics
   - Historical performance charts

### Risk Management Setup

1. **Configure Limits**
   - Open Risk Management tab
   - Set maximum position size percentage
   - Configure daily loss limits
   - Choose risk scenario (Conservative/Moderate/Aggressive)

2. **Enable Monitoring**
   - Start Live Monitoring from the control panel
   - System monitors all positions continuously
   - Automatic alerts for risk threshold breaches
   - Real-time risk assessment display

### Cost Analysis Usage

1. **Select Performance Tier**
   - Choose from Budget, Professional, or Enterprise
   - Review monthly cost breakdowns
   - Analyze infrastructure, data, and operational costs

2. **Plan Investment Strategy**
   - Calculate break-even trading volumes
   - Compare cost efficiency across tiers
   - Project annual operational expenses

## Troubleshooting

### Common Issues

#### Application Won't Start
**Problem:** PowerTraderAI+ shortcut doesn't launch the application

**Solutions:**
1. Verify Python installation:
   ```cmd
   python --version
   ```
2. Re-run the setup script:
   - Double-click "PowerTraderAI+ Setup" desktop shortcut
   - Wait for completion, then try launching again

3. Check installation path:
   - Navigate to `%USERPROFILE%\PowerTraderAI+`
   - Ensure all files are present
   - Try running `PowerTrader_AI.bat` directly

#### Python Package Errors
**Problem:** Import errors or missing package messages

**Solutions:**
1. Re-run environment setup:
   ```cmd
   cd "%USERPROFILE%\PowerTraderAI+"
   setup_environment.bat
   ```

2. Manual package installation:
   ```cmd
   python -m pip install -r app\requirements.txt
   ```

3. Virtual environment setup (advanced):
   ```cmd
   python -m venv venv
   venv\Scripts\activate
   pip install -r app\requirements.txt
   ```

#### GUI Display Issues
**Problem:** Interface appears corrupted or unresponsive

**Solutions:**
1. Check display scaling:
   - Right-click desktop > Display settings
   - Set scaling to 100% if using high DPI

2. Update graphics drivers:
   - Visit manufacturer website for latest drivers
   - Restart computer after installation

3. Clear application cache:
   - Delete `hub_data` folder contents
   - Restart application

#### Trading Features Not Working
**Problem:** Cannot execute trades or see real-time data

**Solutions:**
1. Initialize account first:
   - Open Trading Control Panel
   - Click "Initialize Account"
   - Wait for confirmation message

2. Check internet connection:
   - Ensure stable broadband connection
   - Check firewall settings for Python applications

3. Verify configuration:
   - Open `config\settings.json`
   - Ensure all settings are valid JSON format

### Error Logs

Application logs are stored in the `logs` directory:
- `powertrader.log`: Main application log
- Rotated logs: `powertrader.log.1`, `powertrader.log.2`, etc.

To enable debug logging:
1. Edit `config\logging_config.json`
2. Change log level from "INFO" to "DEBUG"
3. Restart application

## Advanced Features

### Auto-Updater

PowerTraderAI+ includes an automatic update system:

- **Automatic Checks:** Daily update checking (configurable)
- **Background Downloads:** Updates downloaded automatically
- **Backup Creation:** Previous version backed up before updates
- **Rollback Support:** Ability to restore previous versions

To configure updates:
1. Open `config\update_settings.json`
2. Modify settings as needed:
   ```json
   {
     "auto_check": true,
     "check_interval_hours": 24,
     "auto_download": true,
     "auto_install": false
   }
   ```

### Data Export

Export trading data for analysis:
- **Trade History:** `hub_data\trade_history.jsonl`
- **Account Values:** `hub_data\account_value_history.jsonl`
- **P&L Ledger:** `hub_data\pnl_ledger.json`

### Custom Indicators

Advanced users can add custom trading indicators:
1. Create Python files in the `neural_data` directory
2. Follow the existing pattern for indicator development
3. Restart application to load new indicators

## Security Considerations

### Data Protection
- All trading data stored locally on your computer
- No cloud synchronization by default
- Encrypted configuration files (if enabled)

### Network Security
- Firewall configuration may be required
- HTTPS connections for all external data feeds
- No sensitive credentials stored in plain text

### Backup Recommendations
1. Regular backup of entire `PowerTraderAI+` folder
2. Export critical configuration files weekly
3. Store backups on external media or cloud storage

## Performance Optimization

### Memory Usage
- Close unused browser tabs while trading
- Monitor system memory usage
- Consider 16 GB+ RAM for optimal performance

### CPU Optimization
- Close unnecessary background applications
- Use SSD storage for better I/O performance
- Regular system maintenance (disk cleanup, defrag)

### Network Optimization
- Use ethernet connection when possible
- Ensure stable internet with low latency
- Monitor for connection interruptions

## Support and Updates

### Getting Help
1. **Documentation:** This guide and in-app help
2. **Log Files:** Check `logs` directory for error details
3. **Community:** GitHub repository for issues and discussions
4. **Email Support:** For critical issues and bug reports

### Version Updates
- **Stable Channel:** Tested releases (recommended)
- **Beta Channel:** Preview features with testing
- **Alpha Channel:** Cutting-edge development builds

### Contribution
PowerTraderAI+ is open-source software. Contributions welcome:
- Bug reports via GitHub issues
- Feature requests and suggestions
- Code contributions through pull requests

---

## Appendix

### A. File Structure
```
PowerTraderAI+/
├── app/                    # Application files
│   ├── pt_desktop_app.py  # Main application launcher
│   ├── pt_hub.py          # Core GUI interface
│   ├── pt_*.py            # Phase 4 components
│   └── requirements.txt   # Python dependencies
├── config/                # Configuration files
│   ├── settings.json      # Main application settings
│   └── logging_config.json # Logging configuration
├── data/                  # Application data
├── neural_data/           # Neural network data
├── hub_data/             # Trading data and history
├── logs/                 # Application log files
├── PowerTrader_AI.bat    # Application launcher script
└── setup_environment.bat # Environment setup script
```

### B. Default Settings Reference

| Setting | Default Value | Description |
|---------|---------------|-------------|
| Initial Balance | $10,000 | Paper trading starting balance |
| Commission Rate | 0.1% | Trading commission simulation |
| Max Position Size | 20% | Maximum position as % of portfolio |
| Max Daily Loss | 5% | Daily loss limit as % of portfolio |
| Risk Per Trade | 2% | Recommended risk per individual trade |
| Refresh Interval | 10 seconds | Data update frequency |

### C. Supported Assets

**Cryptocurrencies:**
- BTC (Bitcoin)
- ETH (Ethereum) 
- ADA (Cardano)
- DOT (Polkadot)
- MATIC (Polygon)

*Additional assets can be configured in settings.json*

### D. System Resources

**Typical Resource Usage:**
- **RAM:** 200-500 MB during normal operation
- **CPU:** 2-5% during data updates
- **Storage:** 50-100 MB for logs and data (grows over time)
- **Network:** 1-5 MB/hour for market data

---

*PowerTraderAI+ Desktop v4.0.0 - Installation and User Guide*  
*Last Updated: {current_date}*  
*© 2024 PowerTraderAI+ Team*