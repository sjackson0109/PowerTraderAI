"""Honest backtesting harness. Run with ``python -m app.backtest`` (see ``cli.py``)."""

import os
import sys

# The app modules use flat imports (``import trading_mode``); make them resolvable
# when this package is started as ``python -m app.backtest`` from the repo root.
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
