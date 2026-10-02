# Getting Started with PowerTraderAI+

This comprehensive guide will walk you through the complete setup and configuration of PowerTraderAI+.

## System Prerequisites

### Hardware Requirements
- **CPU**: Multi-core processor (Intel i5/AMD Ryzen 5 or equivalent)
- **Memory**: 8GB RAM minimum, 16GB recommended for large portfolios
- **Storage**: 2GB free disk space for application and dependencies
- **Display**: 1920x1080 minimum resolution for optimal GUI experience
- **Network**: Stable broadband internet connection (required for market data)

### Software Requirements
- **Python 3.11+** (Python 3.13 strongly recommended)
  - Download from: https://python.org/downloads/
  - Ensure "Add Python to PATH" is checked during installation
- **Git** (for repository cloning)
  - Windows: https://git-scm.com/download/win
  - macOS: Install via Xcode Command Line Tools or Homebrew
  - Linux: Use package manager (e.g., `sudo apt install git`)
- **Operating System**:
  - Windows 10/11 (fully tested)
  - macOS 10.15+ (compatible)
  - Ubuntu 18.04+ or equivalent Linux distribution

### Account Prerequisites
- **Exchange Accounts** (optional for live trading):
  - Supported exchanges: 110+ via CCXT library
  - API keys required for live trading
  - Demo/testnet accounts recommended for initial testing
- **OpenAI Account** (optional for LLM research features):
  - API key required for AI-powered market analysis
  - Pay-per-use pricing model

## Installation Process

### Method 1: Automated Installation (Recommended)

```bash
# Step 1: Clone the repository
git clone <repository-url>
cd PowerTrader_AI

# Step 2: Create virtual environment (CRITICAL for dependency isolation)
python -m venv .venv

# Step 3: Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Step 4: Install all dependencies automatically
python install_dependencies.py

# Step 5: Launch PowerTrader AI+
cd app
python pt_hub.py
```

### Method 2: Manual Installation

```bash
# Follow steps 1-3 from Method 1, then:

# Install dependencies manually
pip install -r requirements.txt --no-warn-script-location --upgrade

# Verify critical dependencies
python -c "import flask, openai, ccxt, matplotlib, pandas; print('All critical packages installed!')"

# Launch application
cd app
python pt_hub.py
```

### Method 3: One-Command Setup (Advanced Users)

```bash
# Complete installation in single command
git clone <repository-url> && cd PowerTrader_AI && python -m venv .venv && .venv\Scripts\activate && python install_dependencies.py && echo "Installation complete! Run: cd app && python pt_hub.py"
```

## Installation Verification

### Quick System Check
```bash
# Verify Python version
python --version  # Should show 3.11 or higher

# Check virtual environment
python -c "import sys; print('✓ Virtual env active' if hasattr(sys, 'real_prefix') or sys.base_prefix != sys.prefix else '✗ No virtual env detected')"

# Test core dependencies
python -c "
try:
    import flask, openai, ccxt, matplotlib, pandas, numpy
    print('✓ All core dependencies available')
except ImportError as e:
    print(f'✗ Missing dependency: {e}')
"

# Verify application startup
cd app && python -c "from pt_hub import PowerTraderHub; print('✓ PowerTrader Hub can be imported')"
```

### Expected Output
Successful installation should show:
```
PowerTrader AI+ Dependency Installer
==================================================
Virtual environment detected

Installing dependencies...
   This process is completely automated and warning-free
All dependencies installed successfully!

Verifying installation...
  [OK] Flask web framework
  [OK] OpenAI API client  
  [OK] Exchange integration
  [OK] Web scraping

PowerTrader AI+ is ready to run!

Next steps:
   1. cd app
   2. python pt_hub.py
```

## Initial Configuration

### 1. First-time Setup Wizard

When you run PowerTraderAI+ for the first time, you'll be guided through:

- Exchange API configuration
- Basic trading parameters
- Security settings
- Initial balance setup

### 2. Configuration Files

PowerTraderAI+ keeps its files in your per-user folders, not in the program folder
(see [Where your data lives](../../README.md#where-your-data-lives)):

- Config folder: `gui_settings.json` (GUI preferences), `pt_config.json` (trading mode,
  strategy, risk), `trading_config.json` (exchange selection, no keys)
- Log folder: application logs and audit trails
- API keys: the operating system's credential store, never a file

## Quick Start Guide

### Launch the Application

```bash
python pt_hub.py
```

### Initial Setup Steps

1. **Configure Exchanges**: Set up your preferred exchange connections from 65+ supported providers
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
