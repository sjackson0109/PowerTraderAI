# PowerTrader AI+

**Enterprise-Grade AI Trading Platform**

PowerTrader AI+ is a comprehensive, institutional-quality trading platform that combines advanced machine learning algorithms with professional-grade trading infrastructure. Built for both individual traders and enterprise deployment.

## Key Features

### **AI-Powered Trading**
- Advanced neural network trading algorithms
- Real-time market analysis and prediction
- Automated strategy optimization
- Multi-exchange support with unified interface

### **Institutional Trading**
- High-volume order processing and batch execution
- Algorithmic trading (TWAP, VWAP, Iceberg orders)
- Advanced risk management and compliance monitoring
- Professional audit trails and regulatory reporting

### **Advanced Analytics**
- Portfolio optimization using Modern Portfolio Theory
- Comprehensive backtesting framework with Monte Carlo simulation
- Performance attribution analysis (Brinson attribution)
- Real-time market data integration and visualization

### Quick Navigation
- **[📦 Complete Installation Guide](docs/INSTALLATION.md)** - Comprehensive setup with troubleshooting
- **[User Guide](docs/user-guide/README.md)** - How to use the application
- **[Exchange Setup](docs/exchanges/README.md)** - 65+ cryptocurrency exchange configuration
- **[Security Guide](docs/security/README.md)** - Security best practices
- **[API Configuration](docs/api-configuration/README.md)** - Detailed API setup
- **[Troubleshooting](docs/troubleshooting/README.md)** - Common issues and solutions

### **Enterprise Features**
- Order management system with advanced order types
- LLM-powered research and market analysis
- Long-term holdings management and portfolio analytics
- Comprehensive compliance and audit system

## Quick Start

### Prerequisites
- **Python 3.11+** (Python 3.13 recommended for optimal performance)
- **Git** for repository cloning
- **Virtual environment support** (venv, conda, etc.)
- **Windows 10/11, macOS, or Linux** (Windows tested)
- **8GB RAM minimum** (16GB recommended for large portfolios)
- **Internet connection** for market data and package installation

### System Requirements
- **CPU**: Multi-core processor (Intel i5/AMD Ryzen 5 or better)
- **Memory**: 8GB RAM minimum, 16GB recommended
- **Storage**: 2GB free disk space for application and data
- **Network**: Stable broadband internet connection
- **Display**: 1920x1080 minimum resolution recommended

### Installation
```bash
# Clone the repository
git clone https://github.com/sjackson0109/PowerTraderAI
cd PowerTraderAI

# Create and activate virtual environment (STRONGLY recommended)
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/Mac

# Install all dependencies (automatic, warning-free)
python install_dependencies.py

# Alternative: Manual installation
pip install -r requirements.txt --no-warn-script-location --upgrade

# Verify installation
python -c "import flask, openai, ccxt; print('All dependencies installed successfully!')"

# Smoke-test paper trading first (no GUI, no keys; needs internet for the live price)
cd app
python demo_paper_trading.py

# Launch PowerTrader AI+
python pt_hub.py
```

### Quick Installation (One-Command Setup)
```bash
# For experienced users - complete setup in one command
git clone https://github.com/sjackson0109/PowerTraderAI && cd PowerTraderAI && python -m venv .venv && .venv\Scripts\activate && python install_dependencies.py && cd app && python pt_hub.py
```

### Troubleshooting Installation
If you encounter issues:
```bash
# Check Python version (must be 3.11+)
python --version

# Verify virtual environment
python -c "import sys; print('Virtual env active:' if hasattr(sys, 'real_prefix') or sys.base_prefix != sys.prefix else 'No virtual env')"

# Clean reinstall
rm -rf .venv  # Linux/Mac
rmdir /s .venv  # Windows
python -m venv .venv
.venv\Scripts\activate
python install_dependencies.py
```

### Desktop Application

```bash
# Windows: double-click start_powertrader.bat, or run directly:
start_powertrader.bat

# Alternatively, launch the hub directly:
python app/pt_hub.py
```

## Where your data lives

The program folder (this repository, or wherever PowerTrader is installed) is **read-only** while
PowerTrader runs: it holds code and shipped defaults only. Your settings, data and logs live in the
standard per-user folders for your operating system, and your API keys live in the operating system's
credential store, never in a file.

| Kind | Windows | macOS | Linux |
|---|---|---|---|
| Program | install or repo folder | install or repo folder | install or repo folder |
| Config | `%APPDATA%\SJackson\PowerTraderAI\` | `~/Library/Application Support/PowerTraderAI/` | `~/.config/PowerTraderAI/` |
| Data | `%LOCALAPPDATA%\SJackson\PowerTraderAI\` | `~/Library/Application Support/PowerTraderAI/` | `~/.local/share/PowerTraderAI/` |
| Logs | `%LOCALAPPDATA%\SJackson\PowerTraderAI\Logs\` | `~/Library/Logs/PowerTraderAI/` | `~/.local/state/PowerTraderAI/log/` |
| Cache | `%LOCALAPPDATA%\SJackson\PowerTraderAI\Cache\` | `~/Library/Caches/PowerTraderAI/` | `~/.cache/PowerTraderAI/` |
| Secrets | Windows Credential Manager | Keychain | Secret Service (GNOME Keyring, KWallet) |

* **Config**: `pt_config.json` (trading mode, strategy, risk), `gui_settings.json` (hub settings),
  `trading_config.json` / `exchange_config.json` (exchange selection, no keys), `migration-report.md`.
* **Data**: `hub_data/` (trader status, trade history, paper account, `models/` neural files) and the
  SQLite databases.
* **Logs**: application, audit and security logs. **Cache**: downloaded candles and market data (safe to
  delete).
* **Secrets**: API keys, API secrets, private keys and passphrases, entered in the exchange setup window
  (or the Robinhood wizard). For headless or CI use, set them as environment variables instead
  (`POWERTRADER_<EXCHANGE>_API_KEY`, `POWERTRADER_<EXCHANGE>_API_SECRET`,
  `POWERTRADER_<EXCHANGE>_PASSPHRASE`; Robinhood: `POWERTRADER_ROBINHOOD_API_KEY`,
  `POWERTRADER_ROBINHOOD_PRIVATE_KEY`). Environment variables take precedence over the keyring. The full
  table is at the top of [`app/pt_secrets.py`](app/pt_secrets.py). If the system has no credential store,
  PowerTrader stores nothing, tells you which variables to set, and stays in paper mode.
* **Settings → Paths** in the hub shows the folders in use, each with an **Open folder** button.
* Set `POWERTRADER_HOME` to keep everything (`config/`, `data/`, `logs/`, `cache/`) under one folder, for
  development or a portable install.

**Upgrading from an older version:** on first start PowerTrader copies settings, data and keys it finds
in the program folder (`app/pt_config.json`, `app/trading_config.json`, `app/hub_data/`, the Robinhood key
files, ...) to the new locations. It never overwrites or replaces anything already there, writes a
`migration-report.md` to the config folder, and deletes nothing in the old location until you press
**Remove old files** (or run `python app/pt_migrate.py --remove-old-files`) and confirm. The only old
files it can change on its own: a Robinhood key vault saved with the old encryption is re-encrypted in
place when it is read (with its `.pt_cred_meta`). If an old
file differs from the file already in the new location, both are kept: PowerTrader keeps using the file
that was there, and the old one is copied next to it as `<name>.conflict-app.<ext>` (from `app/`) or
`<name>.conflict-root.<ext>` (from the install folder), for example `pt_config.conflict-app.json`
(`-2`, `-3`, ... if that name is taken). So a conflict never rolls a setting back or switches paper
trading to live. If both old folders hold a different version of a file the new location does not have
yet (for example `logs/powertrader.log`), the newer one gets the normal name and the older one the
`.conflict-` name. Both files of each conflict are listed in `migration-report.md` and in the window
shown at start-up; compare them and copy over what you need. A conflict copy of a config file holds no
keys, and keys already in the credential store are never replaced. Even with **Remove old files**, it
deletes an old file only if the file is unchanged since it was copied, its copy (for a conflict, its
`.conflict-` copy) still exists in the new location and it is not read-only. A database goes together with its `-wal`/`-shm`/`-journal` files; if one of
them cannot be deleted, the database is kept. Every file it keeps is listed with the reason. In a git
checkout `app/pt_config.json` and `app/gui_settings.json` are always kept, because other branches still
use them. Files in the folders PowerTrader uses now (for example `data/` and `logs/` when
`POWERTRADER_HOME` is the install root) are never treated as old files. Files reached through a link or
junction are neither copied nor removed, and an old config file that is the same file as the one in use
(a hard link or link) is left alone. An old file that holds keys (the Robinhood key files and their
`.bak` copies, the old vault, `trading_config.json`, ...) is removed only when every key in it is in the
credential store with the same value; otherwise it is kept and the window names the key that differs or
is missing (never its value). To import a config file from
somewhere else (for example a backup): `python app/pt_migrate.py --from <path>`.

## 📁 Project Structure

```
PowerTraderAI/
├── README.md                 # Main project documentation (this file)
├── requirements.txt          # Python dependencies
├── LICENSE                   # Project license
├── start_powertrader.bat     # Windows launcher
│
├── app/                      # Main application code
│   ├── pt_hub.py            # Core PowerTrader Hub (main entry point)
│   ├── pt_api_server.py     # Headless server entry point (Docker/VPS)
│   ├── institutional_trading.py     # Enterprise trading engine
│   ├── compliance_audit_system.py  # Regulatory compliance
│   ├── portfolio_optimizer.py      # Modern Portfolio Theory
│   ├── backtesting_engine.py       # Strategy backtesting
│   ├── performance_attribution.py   # Attribution analysis
│   └── [other modules...]    # Additional trading components
│
└── docs/                     # Complete documentation
    ├── README.md            # Documentation index
    ├── README_DESKTOP.md    # Desktop application guide
    ├── setup/               # Setup and configuration guides
    ├── guides/              # User guides and tutorials
    ├── reference/           # API reference and quick guides
    ├── features/            # Feature-specific documentation
    ├── validation/          # Testing and validation reports
    ├── getting-started/     # Installation and first steps
    ├── user-guide/          # Detailed user documentation
    ├── development/         # Development and release notes
    ├── technical/           # Technical specifications
    ├── security/            # Security guidelines
    ├── troubleshooting/     # Common issues and solutions
    └── [other docs...]      # Additional documentation
```

## 📋 System Requirements

- **Python**: 3.11 or higher (3.13 recommended)
- **Operating System**: Windows 10/11 (primary), macOS, or Linux
- **Memory**: 8GB RAM minimum (16GB recommended)
- **Storage**: 2GB free space
- **Network**: Internet connection for market data

## 💡 Getting Started

1. **Installation**: Follow the setup instructions in [`docs/getting-started/installation.md`](docs/getting-started/installation.md)
2. **Configuration**: Configure your exchange APIs using [`docs/setup/CREDENTIAL_SETUP.md`](docs/setup/CREDENTIAL_SETUP.md)
3. **User Guide**: Read the comprehensive user guide at [`docs/user-guide/README.md`](docs/user-guide/README.md)
4. **Desktop App**: Launch the desktop interface with [`docs/user-guide/DESKTOP_INSTALLATION_GUIDE.md`](docs/user-guide/DESKTOP_INSTALLATION_GUIDE.md)

## 🔧 Advanced Features

- **Institutional Trading**: Enterprise-grade order management and execution
- **Risk Management**: Multi-layered risk controls and compliance monitoring
- **Analytics Suite**: Portfolio optimization, backtesting, and performance analysis
- **AI Research**: LLM-powered market research and analysis tools
- **Multi-Exchange**: Unified interface for multiple cryptocurrency exchanges

## 📖 Documentation

Complete documentation is available in the [`docs/`](docs/) directory:

- **[Setup Guides](docs/setup/)** - Configuration and credentials
- **[User Guides](docs/guides/)** - Step-by-step tutorials
- **[Feature Documentation](docs/features/)** - Detailed feature explanations
- **[API Reference](docs/reference/)** - Technical reference materials
- **[Development](docs/development/)** - Development and contribution guides

## 🤝 Contributing

We welcome contributions! Please see [`docs/reference/CONTRIBUTORS.md`](docs/reference/CONTRIBUTORS.md) for guidelines.

## 📄 License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.

## 🔗 Quick Links

- **[API Reference](docs/reference/API_REFERENCE.md)** - Complete API documentation
- **[Quick Reference](docs/reference/QUICK_REFERENCE.md)** - Command quick reference
- **[Exchange Setup](docs/reference/EXCHANGE_DOCUMENTATION.md)** - Exchange configuration
- **[Troubleshooting](docs/troubleshooting/)** - Common issues and solutions

---

**PowerTrader AI+** - Professional AI Trading Platform
*Version 6.0+ | Enterprise Ready | Institutional Grade*
