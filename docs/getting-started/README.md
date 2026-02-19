# Getting Started with PowerTrader AI

This guide will walk you through the initial setup and configuration of PowerTrader AI.

## Prerequisites

- Python 3.8 or higher
- Windows 10/11 (current configuration)
- Internet connection for market data and trading
- KuCoin account for market data
- Robinhood account for trading execution

## Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/sjackson0109/PowerTraderAI.git
cd PowerTraderAI
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Verify Installation

```python
python pt_hub.py
```

If the GUI launches successfully, your installation is complete.

## Initial Configuration

### 1. First-time Setup Wizard

When you run PowerTrader AI for the first time, you'll be guided through:

- Exchange API configuration
- Basic trading parameters
- Security settings
- Initial balance setup

### 2. Configuration Files

PowerTrader AI creates several configuration files:

- `gui_settings.json` - GUI preferences and settings
- `credentials/` - Encrypted API keys and authentication
- `logs/` - Application logs and audit trails

## Quick Start Guide

### Launch the Application

```bash
python pt_hub.py
```

### Initial Setup Steps

1. **Configure Exchanges**: Set up your KuCoin and Robinhood connections
2. **Set Trading Parameters**: Configure your DCA strategy and risk limits
3. **Fund Your Account**: Add funds to your Robinhood trading account
4. **Start Monitoring**: Begin with paper trading to test your strategy

## Verification Checklist

- [ ] Python installation verified (3.8+)
- [ ] All dependencies installed successfully
- [ ] Application launches without errors
- [ ] Exchange accounts created and verified
- [ ] API keys generated and configured
- [ ] Initial funding completed
- [ ] Test trade executed successfully

## Next Steps

- [User Guide](../user-guide/README.md) - Learn how to use the application
- [Exchange Setup](../exchanges/README.md) - Detailed exchange configuration
- [Security Guidelines](../security/README.md) - Secure your trading setup

## Troubleshooting

Common installation issues:

- **Module not found**: Ensure all requirements are installed
- **Permission errors**: Run as administrator if needed
- **Network issues**: Check firewall and antivirus settings

For more help, see [Troubleshooting Guide](../troubleshooting/README.md).