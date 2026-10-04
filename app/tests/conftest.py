"""Make the flat app modules (trading_mode, pt_trader, ...) importable from app/tests/,
and load the test isolation (isolation.py) here too: pytest started inside
app/tests takes that folder as its root and never reads app/conftest.py."""

import importlib.util
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def _load_isolation():
    """isolation.py, loaded once per session under one name (app/conftest.py
    and .github/scripts/conftest.py load the same module)."""
    name = "powertrader_test_isolation"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(TESTS_DIR, "isolation.py")
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]
            raise
    return sys.modules[name]


_isolation = _load_isolation()
isolated_user_dirs = _isolation.isolated_user_dirs
memory_keyring = _isolation.memory_keyring
