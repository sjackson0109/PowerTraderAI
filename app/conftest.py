"""Test isolation for every test under app/ (FDS-108a). The guard itself is
tests/isolation.py, shared with .github/scripts/conftest.py: loading it sets
``POWERTRADER_HOME``, the keyring backends and the blocked real folders before
any test module is imported, and its autouse fixture isolates every test.
"""

import importlib.util
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def _load_isolation():
    """tests/isolation.py, loaded once per session under one name."""
    name = "powertrader_test_isolation"
    if name not in sys.modules:
        path = os.path.join(APP_DIR, "tests", "isolation.py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]
            raise
    return sys.modules[name]


_isolation = _load_isolation()
RealLocationTouched = _isolation.RealLocationTouched
real_platform_dirs = _isolation.real_platform_dirs
isolated_user_dirs = _isolation.isolated_user_dirs
memory_keyring = _isolation.memory_keyring
