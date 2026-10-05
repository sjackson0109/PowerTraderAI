"""#136: no test under app/ contains a hard-coded user path, such as a folder in
someone's Windows profile or a POSIX home folder. Tests build paths from
pt_paths, POWERTRADER_HOME or tmp_path instead.

The patterns are assembled from pieces, so this file never matches itself."""

import glob
import os
import re

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEXT_SUFFIXES = (
    ".py",
    ".json",
    ".csv",
    ".txt",
    ".cfg",
    ".ini",
    ".yml",
    ".yaml",
    ".toml",
)

_SEP = r"[\\/]+"
_NAME = r"[^\\/\s'\"%$<>{}]+"
_END = r"(?=[\\/'\"\s]|$)"
PATTERNS = (
    # C:\Users\<name>, C:/Users/<name>
    re.compile(r"\b[A-Za-z]:" + _SEP + "Users" + _SEP + _NAME, re.IGNORECASE),
    # \Users\<name> without a drive (valid on Windows)
    re.compile(r"(?<![\w.:$])[\\/]" + "Users" + _SEP + _NAME + _END),
    # POSIX and macOS home folders, and the root user's home folder
    re.compile(r"(?<![\w.~$])/" + "home" + "/" + _NAME + _END),
    re.compile(r"(?<![\w.~$])/" + "Users" + "/" + _NAME + _END),
    re.compile(r"(?<![\w.~$])/" + "root" + _END),
)


def scanned_files():
    """Every test file under app/: the conftest, app/test_*.py and everything in
    app/tests (helpers and fixtures included)."""
    files = [os.path.join(APP_DIR, "conftest.py")]
    files += sorted(glob.glob(os.path.join(APP_DIR, "test_*.py")))
    for folder, dirs, names in os.walk(os.path.join(APP_DIR, "tests")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        files += [
            os.path.join(folder, n) for n in sorted(names) if n.endswith(TEXT_SUFFIXES)
        ]
    return files


def hard_coded_user_paths(lines):
    return [
        (number, line.strip())
        for number, line in enumerate(lines, 1)
        if any(p.search(line) for p in PATTERNS)
    ]


def test_no_test_under_app_contains_a_hard_coded_user_path():
    hits = []
    files = scanned_files()
    assert len(files) > 50  # the scan really covers the test tree
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as f:
            for number, line in hard_coded_user_paths(f):
                hits.append(f"{os.path.relpath(path, APP_DIR)}:{number}: {line}")
    assert hits == []


def test_the_check_finds_hard_coded_user_paths():
    windows = (
        "app_dir = r'C:" + "\\" + "Users" + "\\" + "Someone" + "\\PowerTrader\\app'"
    )
    forward = "folder = 'c:/" + "users/" + "someone/data'"
    driveless = "folder = r'\\" + "Users\\" + "someone\\data'"
    posix = "path = '/" + "home/" + "someone/.config/x'"
    posix_bare = "monkeypatch.setenv('HOME', '/" + "home/" + "someone')"
    mac = "path = '/" + "Users/" + "someone/Library/x'"
    mac_bare = 'os.path.join("/' + "Users/" + 'someone", ".config")'
    root = "path = '/" + "root/.config/x'"
    for line in (windows, forward, driveless, posix, posix_bare, mac, mac_bare, root):
        assert hard_coded_user_paths([line]) == [(1, line)], line
    # placeholders and environment lookups are not hard-coded paths
    allowed = (
        "r'%APPDATA%\\SJackson\\PowerTraderAI'",
        "'~/Library/Application Support/PowerTraderAI/'",
        "appdata = os.environ['APPDATA']",
        "pt_paths.models_dir()",
        "url = 'https://api.example.com/users/me'",
        "legacy_root = tmp_path / 'pt_legacy_root'",
    )
    for line in allowed:
        assert hard_coded_user_paths([line]) == [], line
