"""Test isolation (FDS-108a), shared by every test under app/ (app/conftest.py)
and under .github/scripts (.github/scripts/conftest.py). Both conftests load
this file by path under one module name (``powertrader_test_isolation``), so
its set-up runs once per session, before any test module is imported:

* ``POWERTRADER_HOME`` points at a temp folder, so config, data, logs and cache
  never resolve to the real ``%APPDATA%`` / ``~/.config`` locations. It is set
  when this module is imported (before any test module computes a path at
  import time) and again, fresh, for every test.
* The keyring is an in-memory backend, fresh for every test. Child processes
  get ``PYTHON_KEYRING_BACKEND`` = the "fail" backend, so nothing a test starts
  can read the real credential store either.
* Resolving the real platform folders raises inside tests, and a guard checks
  after every test that the real folders were not created or changed.
* The legacy (pre-FDS-108a) locations (``app/`` and the install root) are
  empty temp folders, so the migration never reads the developer's real
  ``app/pt_config.json`` or databases.
"""

import os
import sys
import tempfile

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_SESSION_HOME = tempfile.mkdtemp(prefix="pt_test_home_")
os.environ["POWERTRADER_HOME"] = _SESSION_HOME
os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.fail.Keyring"

import pt_paths  # noqa: E402

_real_platform_dir = pt_paths._platform_dir


class RealLocationTouched(AssertionError):
    pass


def _blocked_platform_dir(kind):
    raise RealLocationTouched(
        f"a test resolved the real {kind!r} folder; tests must use POWERTRADER_HOME"
    )


pt_paths._platform_dir = _blocked_platform_dir


def real_platform_dirs():
    """The real per-user folders (strings only; nothing is created or read)."""
    return {
        kind: _real_platform_dir(kind) for kind in ("config", "data", "log", "cache")
    }


def _snapshot(paths):
    state = {}
    for path in paths:
        try:
            st = os.stat(path)
            state[path] = (True, st.st_mtime_ns)
        except OSError:
            state[path] = (False, None)
    return state


_REAL_DIRS = sorted(set(real_platform_dirs().values()))

try:
    import keyring
    from keyring.backend import KeyringBackend
    from keyring.errors import PasswordDeleteError
except ImportError:  # keyring not installed: secrets tests will fail loudly on import
    keyring = None
    KeyringBackend = object

if keyring is not None:

    from jaraco.classes import properties

    class MemoryKeyring(KeyringBackend):
        """In-memory keyring for tests. Never auto-selected (priority raises,
        which keyring treats as "not viable")."""

        @properties.classproperty
        def priority(cls):
            raise RuntimeError("test-only backend; set explicitly")

        def __init__(self):
            super().__init__()
            self.entries = {}

        def get_password(self, service, username):
            return self.entries.get((service, username))

        def set_password(self, service, username, password):
            self.entries[(service, username)] = password

        def delete_password(self, service, username):
            try:
                del self.entries[(service, username)]
            except KeyError:
                raise PasswordDeleteError(username)

    keyring.set_keyring(MemoryKeyring())


@pytest.fixture(autouse=True)
def isolated_user_dirs(tmp_path, monkeypatch):
    """Fresh POWERTRADER_HOME, empty legacy folder and empty keyring per test."""
    home = tmp_path / "pt_home"
    legacy = tmp_path / "pt_legacy"
    legacy.mkdir()
    legacy_root = tmp_path / "pt_legacy_root"
    legacy_root.mkdir()
    monkeypatch.setenv("POWERTRADER_HOME", str(home))
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.fail.Keyring")
    monkeypatch.setattr(pt_paths, "legacy_dir", lambda: str(legacy))
    monkeypatch.setattr(pt_paths, "legacy_install_dir", lambda: str(legacy_root))
    memory = None
    if keyring is not None:
        previous = keyring.get_keyring()
        memory = MemoryKeyring()
        keyring.set_keyring(memory)
    before = _snapshot(_REAL_DIRS)
    yield {
        "home": str(home),
        "legacy": str(legacy),
        "legacy_root": str(legacy_root),
        "keyring": memory,
    }
    if keyring is not None:
        keyring.set_keyring(previous)
    after = _snapshot(_REAL_DIRS)
    if after != before:
        changed = [p for p in _REAL_DIRS if before[p] != after[p]]
        pytest.fail(f"test touched the real user folders: {changed}", pytrace=False)


@pytest.fixture
def memory_keyring(isolated_user_dirs):
    """The in-memory keyring installed for this test."""
    return isolated_user_dirs["keyring"]
