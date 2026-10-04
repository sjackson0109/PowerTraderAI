"""Make the flat app modules (trading_mode, pt_trader, ...) importable from app/tests/."""

import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
