# PowerTrader AI Application

This directory contains the core PowerTrader AI application files.

## Directory Structure

```
app/
├── config/                 # Configuration files and settings
├── pt_*.py                 # Core PowerTrader modules
│   ├── pt_desktop_app.py   # Desktop application launcher
│   ├── pt_hub.py           # Main GUI application
│   ├── pt_thinker.py       # Neural network processing
│   ├── pt_trader.py        # Trading engine
│   ├── pt_trainer.py       # ML model training
│   └── ...                 # Additional modules
└── requirements.txt        # Python dependencies
```

## Running the Application

From the project root directory:
```bash
python app/pt_desktop_app.py
```

Or directly from this directory:
```bash
cd app
python pt_desktop_app.py
```

## Dependencies

Install all required packages:
```bash
pip install -r requirements.txt
```

## Module Overview

- **pt_desktop_app.py** - Main desktop application entry point
- **pt_hub.py** - PowerTrader GUI framework
- **pt_thinker.py** - Neural network processing and analysis
- **pt_trader.py** - Trading execution and strategy management
- **pt_trainer.py** - Machine learning model training
- **pt_config.py** - Configuration management
- **pt_security.py** - Security and authentication
- **pt_files.py** - File system operations
- **pt_utils.py** - Utility functions and helpers

---

*PowerTrader AI Application Directory*