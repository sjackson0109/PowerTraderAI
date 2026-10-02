"""
Where PowerTraderAI keeps things (FDS-108a).

This is the ONLY module that knows where config, data, logs and cache live.
Every other module asks it; nothing else builds a path to a user file from
``__file__`` or the current working directory.

======== ======================================== ================================================
Kind     Windows                                  macOS / Linux
======== ======================================== ================================================
Program  the install or repo ``app/`` folder      the install or repo ``app/`` folder
Config   ``%APPDATA%\\SJackson\\PowerTraderAI``    ``~/Library/Application Support/PowerTraderAI``
                                                  / ``~/.config/PowerTraderAI``
Data     ``%LOCALAPPDATA%\\SJackson\\PowerTraderAI`` ``~/Library/Application Support/PowerTraderAI``
                                                  / ``~/.local/share/PowerTraderAI``
Logs     ``<Data>\\Logs``                          ``~/Library/Logs/PowerTraderAI``
                                                  / ``~/.local/state/PowerTraderAI/log``
Cache    ``<Data>\\Cache``                         ``~/Library/Caches/PowerTraderAI``
                                                  / ``~/.cache/PowerTraderAI``
======== ======================================== ================================================

Secrets never live in any of these folders; see ``pt_secrets``.

If ``POWERTRADER_HOME`` is set, everything lives under it instead, as
``config/``, ``data/``, ``logs/`` and ``cache/`` (development, portable use,
tests).

The program directory is read-only at runtime: it holds code and shipped
defaults (``*.example.json`` templates) only. Directories are created lazily,
the first time they are asked for. On macOS and Linux the folders are created
``0700`` and config files ``0600``; on Windows the user-profile ACLs apply.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Dict, Optional

APP_NAME = "PowerTraderAI"
APP_AUTHOR = "SJackson"
HOME_ENV = "POWERTRADER_HOME"

# Files in config_dir().
SETTINGS_FILE = "pt_config.json"
GUI_SETTINGS_FILE = "gui_settings.json"
TRADING_CONFIG_FILE = "trading_config.json"
EXCHANGE_CONFIG_FILE = "exchange_config.json"
MIGRATION_REPORT_FILE = "migration-report.md"

# Directory under data_dir() shared by the hub, trainer, thinker and trader.
HUB_DIR_NAME = "hub_data"
MODELS_DIR_NAME = "models"

_POSIX = os.name == "posix"
_DIR_MODE = 0o700
_FILE_MODE = 0o600


def _platform_dir(kind: str) -> str:
    """The OS-standard folder for ``kind`` ("config", "data", "log", "cache")."""
    import platformdirs

    if kind == "config":
        return platformdirs.user_config_dir(APP_NAME, APP_AUTHOR, roaming=True)
    if kind == "data":
        return platformdirs.user_data_dir(APP_NAME, APP_AUTHOR, roaming=False)
    if kind == "log":
        return platformdirs.user_log_dir(APP_NAME, APP_AUTHOR)
    if kind == "cache":
        return platformdirs.user_cache_dir(APP_NAME, APP_AUTHOR)
    raise ValueError(f"unknown directory kind: {kind!r}")


_HOME_SUBDIRS = {"config": "config", "data": "data", "log": "logs", "cache": "cache"}


def home_override() -> Optional[str]:
    """The ``POWERTRADER_HOME`` folder, or None when it is not set."""
    home = os.environ.get(HOME_ENV, "").strip()
    return os.path.abspath(os.path.expanduser(home)) if home else None


def _resolve(kind: str) -> str:
    home = home_override()
    if home:
        return os.path.join(home, _HOME_SUBDIRS[kind])
    return os.path.abspath(_platform_dir(kind))


def make_private_dir(path: str) -> str:
    """Create ``path`` (and parents) if missing; ``0700`` on macOS/Linux."""
    if not os.path.isdir(path):
        os.makedirs(path, mode=_DIR_MODE, exist_ok=True)
        if _POSIX:
            os.chmod(path, _DIR_MODE)
    return path


def _dir(kind: str, create: bool) -> str:
    path = _resolve(kind)
    return make_private_dir(path) if create else path


def program_dir() -> str:
    """The folder holding the code and shipped defaults. Read-only at runtime:
    no component writes here (the migration only reads legacy files from it)."""
    return os.path.dirname(os.path.abspath(__file__))


def legacy_dir() -> str:
    """Where releases before FDS-108a kept settings, credentials and hub_data
    (next to the code). Only ``pt_migrate`` reads from here."""
    return program_dir()


def config_dir(create: bool = True) -> str:
    return _dir("config", create)


def data_dir(create: bool = True) -> str:
    return _dir("data", create)


def log_dir(create: bool = True) -> str:
    return _dir("log", create)


def cache_dir(create: bool = True) -> str:
    return _dir("cache", create)


def hub_dir(create: bool = True) -> str:
    """``<data>/hub_data``: runner state shared by hub, trainer, thinker, trader."""
    path = os.path.join(data_dir(create), HUB_DIR_NAME)
    return make_private_dir(path) if create else path


def models_dir(create: bool = True) -> str:
    """``<data>/hub_data/models``; one ``<model_id>/`` folder per model."""
    path = os.path.join(hub_dir(create), MODELS_DIR_NAME)
    return make_private_dir(path) if create else path


def config_file(name: str) -> str:
    """Full path of a config file (``name`` is a bare file name)."""
    return os.path.join(config_dir(), _bare(name))


def data_file(*parts: str) -> str:
    """Full path of a file under data_dir(); creates its parent folder."""
    return _under(data_dir(), parts)


def log_file(*parts: str) -> str:
    """Full path of a file under log_dir(); creates its parent folder."""
    return _under(log_dir(), parts)


def cache_file(*parts: str) -> str:
    """Full path of a file under cache_dir(); creates its parent folder."""
    return _under(cache_dir(), parts)


def settings_file() -> str:
    return config_file(SETTINGS_FILE)


def gui_settings_file() -> str:
    return config_file(GUI_SETTINGS_FILE)


def trading_config_file() -> str:
    return config_file(TRADING_CONFIG_FILE)


def exchange_config_file() -> str:
    return config_file(EXCHANGE_CONFIG_FILE)


def shipped_default(name: str) -> str:
    """A read-only template shipped in the program directory."""
    return os.path.join(program_dir(), _bare(name))


def ensure_dirs() -> Dict[str, str]:
    """Create every folder now and return them by kind."""
    return {
        "config": config_dir(),
        "data": data_dir(),
        "logs": log_dir(),
        "cache": cache_dir(),
        "hub_data": hub_dir(),
        "models": models_dir(),
    }


def describe() -> Dict[str, str]:
    """The resolved folders, without creating anything (for the Settings window)."""
    return {
        "program": program_dir(),
        "config": config_dir(create=False),
        "data": data_dir(create=False),
        "logs": log_dir(create=False),
        "cache": cache_dir(create=False),
    }


def secure_file(path: str) -> None:
    """``0600`` on macOS/Linux; no-op on Windows (profile ACLs apply)."""
    if _POSIX and os.path.exists(path):
        os.chmod(path, _FILE_MODE)


def write_private_text(path: str, text: str) -> None:
    """Atomically write a config file readable only by the user.

    The temp file is created ``0600`` before any byte is written, then
    replaces ``path``, so no reader ever sees a half-written file.
    """
    folder = os.path.dirname(os.path.abspath(path))
    make_private_dir(folder)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
    try:
        if _POSIX:
            os.fchmod(fd, _FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    secure_file(path)


def install_default(name: str, target: Optional[str] = None) -> Optional[str]:
    """Copy the shipped ``name`` template into config_dir() on first run.

    Does nothing (and never overwrites) when the target already exists or no
    template is shipped. Returns the target path when a copy was made.
    """
    source = shipped_default(name)
    target = target or config_file(name.replace(".example", ""))
    if os.path.exists(target) or not os.path.isfile(source):
        return None
    make_private_dir(os.path.dirname(target))
    shutil.copyfile(source, target)
    secure_file(target)
    return target


def is_inside_program_dir(path: str) -> bool:
    """True when ``path`` is inside the (read-only) program directory."""
    try:
        common = os.path.commonpath([os.path.abspath(path), program_dir()])
    except ValueError:  # different drives on Windows
        return False
    return os.path.normcase(common) == os.path.normcase(program_dir())


def _bare(name: str) -> str:
    if not name or os.path.basename(name) != name or name in (".", ".."):
        raise ValueError(f"expected a bare file name, got {name!r}")
    return name


def _under(base: str, parts) -> str:
    if not parts:
        raise ValueError("expected at least one path part")
    path = os.path.join(base, *parts)
    if os.path.commonpath([os.path.abspath(path), base]) != base:
        raise ValueError(f"{os.path.join(*parts)!r} escapes {base}")
    make_private_dir(os.path.dirname(path))
    return path
