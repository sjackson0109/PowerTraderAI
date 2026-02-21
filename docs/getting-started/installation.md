# Installation Guide

Comprehensive installation instructions for PowerTraderAI+ on Windows.

## System Requirements

### Minimum Requirements
- **OS**: Windows 10 (1909) or Windows 11
- **Python**: 3.8 or higher
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 2GB free space
- **Network**: Stable internet connection (10+ Mbps recommended)

### Recommended Requirements
- **OS**: Windows 11 with latest updates
- **Python**: 3.10 or 3.11
- **RAM**: 16GB for optimal performance
- **Storage**: SSD with 5GB free space
- **Network**: High-speed internet (50+ Mbps)

## Download and Installation

### Method 1: Git Clone (Recommended)

1. **Install Git** (if not already installed):
   - Download from [git-scm.com](https://git-scm.com/download/win)
   - Run installer with default settings

2. **Clone Repository**:
   ```bash
   git clone https://github.com/sjackson0109/PowerTraderAI.git
   cd PowerTraderAI
   ```

### Method 2: Direct Download

1. **Download ZIP**:
   - Go to [GitHub Repository](https://github.com/sjackson0109/PowerTraderAI)
   - Click "Code" → "Download ZIP"
   - Extract to desired location

## Python Setup

### Install Python

1. **Download Python** from [python.org](https://www.python.org/downloads/)
2. **Installation Options**:
   - Add Python to PATH
   - Install for all users
   - Include pip and IDLE

3. **Verify Installation**:
   ```bash
   python --version
   pip --version
   ```

### Virtual Environment (Optional but Recommended)

```bash
# Create virtual environment
python -m venv powertrader_env

# Activate virtual environment
powertrader_env\Scripts\activate

# Verify activation (prompt should show environment name)
```

## Install Dependencies

### Install Required Packages

```bash
# Navigate to PowerTraderAI+ directory
cd PowerTraderAI

# Install dependencies
pip install -r requirements.txt
```

### Dependency List

The application requires these key packages:
- `tkinter` - GUI framework (included with Python)
- `matplotlib` - Charting and visualization
- `requests` - HTTP client for API calls
- `python-kucoin` - KuCoin API client
- `robin-stocks` - Robinhood API client
- `cryptography` - Encryption for secure storage

### Verify Installation

```python
# Test imports
python -c "import tkinter, matplotlib, requests; print('All dependencies installed successfully')"
```

## First Run

### Launch Application

```bash
python pt_hub.py
```

### Expected Behavior

1. **GUI Window**: Main PowerTraderAI+ interface should appear
2. **Setup Wizard**: First-time configuration dialog
3. **Log Output**: Console should show initialization messages

### Success Indicators

- GUI loads without errors
- Charts render properly
- No missing module errors
- Setup wizard appears

## Configuration

### Initial Setup

The first run will prompt you to configure:

1. **Exchange Connections**:
   - KuCoin API credentials
   - Robinhood login details

2. **Trading Parameters**:
   - Initial balance
   - Risk tolerance
   - DCA strategy settings

3. **Security Settings**:
   - Encryption password
   - Backup options

### Configuration Files

PowerTraderAI+ creates these files during setup:

```
PowerTraderAI/
├── gui_settings.json      # UI preferences
├── credentials/           # Encrypted API keys
│   ├── kucoin_keys.enc
│   └── robinhood_keys.enc
└── logs/                 # Application logs
    ├── powertrader.log
    └── audit.log
```

## Development Environment (Optional)

### IDE Setup

**Recommended IDEs**:
- **VS Code** with Python extension
- **PyCharm** Community Edition
- **Sublime Text** with Python package

### Development Dependencies

For development and testing:

```bash
pip install -r requirements-dev.txt
```

Includes:
- `pytest` - Testing framework
- `black` - Code formatting
- `pylint` - Code analysis

## Troubleshooting Installation

### Common Issues

**1. Python Not Found**
```bash
# Error: 'python' is not recognized
# Solution: Add Python to PATH or use full path
C:\Python39\python.exe pt_hub.py
```

**2. Module Import Errors**
```bash
# Error: ModuleNotFoundError: No module named 'requests'
# Solution: Install requirements
pip install -r requirements.txt
```

**3. Permission Errors**
```bash
# Error: Permission denied
# Solution: Run as administrator
# Right-click Command Prompt → "Run as administrator"
```

**4. Firewall/Antivirus Blocks**
- Add PowerTraderAI+ folder to antivirus exclusions
- Allow Python through Windows Firewall
- Check corporate firewall settings

**5. Network Connectivity**
```bash
# Test internet connection
ping api.kucoin.com
ping robinhood.com
```

### Getting Help

If installation issues persist:

1. **Check System Requirements**: Ensure your system meets minimum specs
2. **Update Python**: Use latest stable version
3. **Clean Install**: Remove and reinstall dependencies
4. **GitHub Issues**: Report bugs with system details

## Support

- **Documentation**: [Full documentation](../README.md)
- **Issues**: [GitHub Issues](https://github.com/sjackson0109/PowerTraderAI/issues)
- **Security**: [Security Guidelines](../security/README.md)

## Installation Complete

Once installation is successful:

1. Python and dependencies installed
2. Application launches correctly
3. Configuration completed
4. Ready for exchange setup

**Next Steps**: [Exchange Setup Guide](../exchanges/README.md)