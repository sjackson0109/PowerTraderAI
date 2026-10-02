"""
Move pre-FDS-108a user files out of the program folder.

Releases before FDS-108a kept settings, credentials, models and runtime data
next to the code (``app/``), and wrote some files relative to the working
directory (the install root when started from ``start_powertrader.bat``).
This module moves them to the locations ``pt_paths`` defines:

1. Non-secret config is copied to ``config_dir()`` (credential fields removed).
2. Credentials go to the OS keyring through ``pt_secrets``.
3. ``hub_data/``, the neural (model) files, databases and logs are copied to
   the data / cache / log folders.
4. ``migration-report.md`` in ``config_dir()`` lists what moved where;
   credentials are named by field only.

Rules:

* A legacy file is never deleted or modified automatically.
  ``remove_legacy_files`` deletes migrated legacy copies only when called with
  ``confirmed=True`` (the hub asks first and warns that they may hold
  plaintext credentials). A legacy file whose content was not migrated (a
  conflict, or a credential that could not be stored) is never offered.
* An existing file in the new location is never overwritten: it is kept and
  the conflict is listed in the report. The same holds for keyring entries.
* Idempotent: every handled item is recorded (size and modification time of
  the legacy file) in ``migration-state.json``; a second run with nothing new
  does nothing. Credentials that could not be stored (no keyring) are retried
  on the next run.

Runs automatically at hub start-up, and as a command::

    python app/pt_migrate.py                      # migrate from the legacy folders
    python app/pt_migrate.py --from <file>        # import one config file from anywhere
    python app/pt_migrate.py --remove-old-files   # delete migrated legacy copies (asks)
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pt_paths  # noqa: E402
import pt_secrets  # noqa: E402

logger = logging.getLogger("pt_migrate")

STATE_FILE = "migration-state.json"

# Legacy config files in the program folder -> same name in config_dir().
CONFIG_FILES = (
    pt_paths.SETTINGS_FILE,
    pt_paths.GUI_SETTINGS_FILE,
    pt_paths.TRADING_CONFIG_FILE,
    pt_paths.EXCHANGE_CONFIG_FILE,
)

# Per-coin neural files (BTC in the legacy root, other coins in <root>/<SYM>/).
NEURAL_PATTERNS = (
    "memories_*.txt",
    "memory_weights*_*.txt",
    "neural_perfect_threshold_*.txt",
    "trainer_status.json",
    "trainer_last_training_time.txt",
    "trainer_last_start_time.txt",
    "low_bound_prices.html",
    "high_bound_prices.html",
    "long_dca_signal.txt",
    "short_dca_signal.txt",
    "signals_dca_*.txt",
    "futures_*profit_margin*.txt",
    "memory.json",
)

# Files the old code wrote next to the code or relative to the working
# directory: (relative source path, destination kind, destination name).
LOOSE_FILES = (
    ("order_management.db", "data", "order_management.db"),
    ("institutional_trading.db", "data", "institutional_trading.db"),
    ("portfolio_optimization.db", "data", "portfolio_optimization.db"),
    ("risk_management.db", "data", "risk_management.db"),
    ("compliance_audit.db", "data", "compliance_audit.db"),
    (os.path.join("data", "automation.db"), "data", "automation.db"),
    (os.path.join("data", "holdings.db"), "data", "holdings.db"),
    (os.path.join("data", "portfolio_analytics.db"), "data", "portfolio_analytics.db"),
    ("market_data.db", "cache", "market_data.db"),
    ("credential_audit.jsonl", "log", "credential_audit.jsonl"),
    ("credential_audit.jsonl.1", "log", "credential_audit.jsonl.1"),
)
SQLITE_SIDECARS = ("-wal", "-shm")

# Robinhood legacy files.
RH_PLAINTEXT = ("r_key.txt", "r_secret.txt")
RH_VAULT = ("r_key.enc", "r_secret.enc", ".pt_salt")
RH_META = ".pt_cred_meta"
RH_BACKUP_PATTERNS = ("r_key.txt.bak_*", "r_secret.txt.bak_*")

PLAINTEXT_WARNING = (
    "These old files may contain your API keys in plain text. Delete them only "
    "after checking PowerTrader works with the migrated settings."
)


@dataclass
class Report:
    """What one migration run did. Credentials are listed as ``exchange:field`` only."""

    copied: List[Tuple[str, str]] = field(default_factory=list)  # (source, target)
    secrets: List[Tuple[str, str]] = field(default_factory=list)  # (source, "exchange:field")
    conflicts: List[Tuple[str, str]] = field(default_factory=list)  # (source, kept target)
    secret_conflicts: List[Tuple[str, str]] = field(default_factory=list)  # (source, entry)
    errors: List[Tuple[str, str]] = field(default_factory=list)  # (source, message)
    removable: List[str] = field(default_factory=list)  # legacy copies safe to delete
    plaintext_left: List[str] = field(default_factory=list)  # legacy files with plaintext secrets
    report_path: Optional[str] = None

    @property
    def changed(self) -> bool:
        return bool(
            self.copied or self.secrets or self.conflicts or self.secret_conflicts or self.errors
        )

    def summary(self) -> str:
        lines = []
        if self.copied:
            lines.append(f"{len(self.copied)} file(s) copied to the new folders")
        if self.secrets:
            lines.append(f"{len(self.secrets)} credential(s) moved to the OS keyring")
        if self.conflicts or self.secret_conflicts:
            lines.append(
                f"{len(self.conflicts) + len(self.secret_conflicts)} conflict(s): "
                "the new location was kept"
            )
        if self.errors:
            lines.append(f"{len(self.errors)} item(s) could not be migrated")
        return "\n".join(lines) or "Nothing to migrate."


# --- state ------------------------------------------------------------------------


def _fingerprint(path: str) -> List[int]:
    st = os.stat(path)
    return [st.st_size, st.st_mtime_ns]


class _State:
    """``{"items": {key: {"fp": [size, mtime_ns], "redundant": bool}}, "removable": [...]}``"""

    def __init__(self):
        self.path = pt_paths.config_file(STATE_FILE)
        self.data = {"items": {}, "removable": []}
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and isinstance(loaded.get("items"), dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass
        self._original = json.dumps(self.data, sort_keys=True)

    def entry(self, key: str, source: str) -> Optional[dict]:
        """The record for ``key`` if the legacy file has not changed since."""
        item = self.data["items"].get(key)
        try:
            if item and item.get("fp") == _fingerprint(source):
                return item
        except OSError:
            pass
        return None

    def mark(self, key: str, source: str, redundant: bool) -> None:
        try:
            self.data["items"][key] = {"fp": _fingerprint(source), "redundant": bool(redundant)}
        except OSError:
            pass

    def save(self) -> None:
        if json.dumps(self.data, sort_keys=True) != self._original:
            pt_paths.write_private_text(self.path, json.dumps(self.data, indent=2, sort_keys=True))


# --- helpers ------------------------------------------------------------------------


def _same_content(a: str, b: str) -> bool:
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    digests = []
    for path in (a, b):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        digests.append(h.digest())
    return digests[0] == digests[1]


def _copy_file(source: str, target: str, report: Report, state: _State) -> bool:
    """Copy one file, never overwriting. True when the legacy copy is redundant
    (copied now or earlier, or already identical at the target)."""
    key = f"file:{source}"
    seen = state.entry(key, source)
    if seen is not None:
        return seen["redundant"] and os.path.exists(target)
    try:
        if os.path.exists(target):
            identical = _same_content(source, target)
            if not identical:
                report.conflicts.append((source, target))
            state.mark(key, source, identical)
            return identical
        pt_paths.make_private_dir(os.path.dirname(target))
        shutil.copy2(source, target)
        report.copied.append((source, target))
        state.mark(key, source, True)
        return True
    except OSError as exc:
        report.errors.append((source, f"copy failed ({type(exc).__name__})"))
        return False


def _write_config(source: str, target: str, data, report: Report, state: _State) -> bool:
    """Write the cleaned config ``data`` to ``target`` unless a file is already there."""
    key = f"config:{source}"
    seen = state.entry(key, source)
    if seen is not None:
        return seen["redundant"]
    if os.path.exists(target):
        report.conflicts.append((source, target))
        state.mark(key, source, False)
        return False
    pt_paths.write_private_text(target, json.dumps(data, indent=2))
    report.copied.append((source, target))
    state.mark(key, source, True)
    return True


def _load_json(path: str, report: Report):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        report.errors.append((path, f"not readable as JSON ({type(exc).__name__})"))
        return None


def _store_secret(exchange: str, field_name: str, value: str, source: str, report: Report) -> str:
    """Put one credential in the keyring unless it already holds a different
    value (the new location wins). Returns "stored", "present", "conflict" or "error"."""
    entry = f"{exchange}:{field_name}"
    try:
        current = pt_secrets._keyring_get(pt_secrets.normalise_exchange(exchange), field_name)
        if current is not None:
            if current == value:
                return "present"
            report.secret_conflicts.append((source, entry))
            return "conflict"
        pt_secrets.set_secret(exchange, field_name, value)
        report.secrets.append((source, entry))
        return "stored"
    except pt_secrets.KeyringUnavailable:
        report.errors.append(
            (source, f"{entry}: no OS keyring available, not moved - set it as an "
                     "environment variable instead (see pt_secrets)")
        )
    except pt_secrets.SecretsError as exc:
        report.errors.append((source, f"{entry}: {exc}"))
    return "error"


def _migrate_secrets(source: str, items: List[Tuple[str, str, str]], report: Report,
                     state: _State) -> bool:
    """Store ``(exchange, field, value)`` items from one legacy file. True when
    every value is now safely in the keyring. Recorded unless something failed,
    so a missing keyring is retried next time."""
    key = f"secrets:{source}"
    seen = state.entry(key, source)
    if seen is not None:
        return seen["redundant"]
    results = [_store_secret(ex, f, v, source, report) for ex, f, v in items if v]
    if "error" not in results:
        state.mark(key, source, "conflict" not in results)
    return all(r in ("stored", "present") for r in results)


def _secret_field(exchange: str, key: str) -> Optional[str]:
    """Keyring field for a legacy credential key (Coinbase ``api_secret`` -> ``private_key``)."""
    try:
        name = pt_secrets.field_for_kwarg(exchange, key)
        if name:
            return name
        return key if any(f.name == key for f in pt_secrets.secret_fields(exchange)) else None
    except pt_secrets.SecretsError:
        return None


def _credential_items(source: str, pairs, report: Report) -> List[Tuple[str, str, str]]:
    items = []
    for exchange, key, value in pairs:
        value = str(value or "").strip()
        if not value:
            continue
        field_name = _secret_field(exchange, key) if exchange else None
        if field_name:
            items.append((exchange, field_name, value))
        else:
            report.errors.append((source, f"{exchange or '?'}.{key}: no keyring field for it, not moved"))
    return items


def _holds_secret(data) -> bool:
    if isinstance(data, dict):
        return any((pt_secrets.is_secret_key(k) and bool(v)) or _holds_secret(v) for k, v in data.items())
    if isinstance(data, list):
        return any(_holds_secret(v) for v in data)
    return False


def _inside(path: str, folder: str) -> bool:
    try:
        path = os.path.normcase(os.path.abspath(path))
        folder = os.path.normcase(os.path.abspath(folder))
        return os.path.commonpath([path, folder]) == folder
    except ValueError:
        return False


def _relocated_gui_settings(data: dict, legacy_roots: Iterable[str]) -> dict:
    """Blank folder settings that pointed into the old program folder (or were
    relative to it): that data moves to the user data folder, whose default
    is then used."""
    out = dict(data)
    for key in ("main_neural_dir", "hub_data_dir"):
        value = str(out.get(key) or "").strip()
        if not value:
            continue
        if (
            not os.path.isabs(value)
            or any(_inside(value, root) for root in legacy_roots)
            or pt_paths.is_inside_program_dir(value)
        ):
            out[key] = ""
    return out


# --- config files ---------------------------------------------------------------------


def _migrate_config(source: str, kind: str, report: Report, state: _State,
                    legacy_roots: Iterable[str]) -> bool:
    """One legacy config file: credentials to the keyring, the rest to the
    config folder. True when the legacy file is now redundant."""
    data = _load_json(source, report)
    if not isinstance(data, (dict, list)):
        return False
    secrets_ok = True
    if kind == pt_paths.TRADING_CONFIG_FILE and isinstance(data, dict):
        pairs = [
            (str(ex.get("exchange_type", "")).strip().lower(), key, ex.get(key))
            for ex in data.get("exchanges", []) or []
            if isinstance(ex, dict)
            for key in ("api_key", "api_secret", "passphrase")
        ]
        secrets_ok = _migrate_secrets(source, _credential_items(source, pairs, report), report, state)
    elif kind == pt_paths.EXCHANGE_CONFIG_FILE and isinstance(data, dict):
        pairs = [
            (str(name).strip().lower(), key, value)
            for name, settings in data.items()
            if isinstance(settings, dict)
            for key, value in settings.items()
            if pt_secrets.is_secret_key(key)
        ]
        secrets_ok = _migrate_secrets(source, _credential_items(source, pairs, report), report, state)
    clean = pt_secrets.strip_secret_fields(data, os.path.basename(source), warn=False)
    if kind == pt_paths.GUI_SETTINGS_FILE and isinstance(clean, dict):
        clean = _relocated_gui_settings(clean, legacy_roots)
    written = _write_config(source, pt_paths.config_file(kind), clean, report, state)
    if _holds_secret(data):
        report.plaintext_left.append(source)
    return written and secrets_ok


def _detect_kind(path: str, report: Report) -> Optional[str]:
    name = os.path.basename(path).lower()
    for known in CONFIG_FILES:
        stem = known[: -len(".json")]
        if name == known or any(name.startswith(stem + sep) for sep in (".", "_", "-", " ")):
            return known
    data = _load_json(path, report)
    if isinstance(data, dict):
        if isinstance(data.get("exchanges"), list):
            return pt_paths.TRADING_CONFIG_FILE
        if "trading" in data or "strategy" in data:
            return pt_paths.SETTINGS_FILE
        if "coins" in data or "main_neural_dir" in data:
            return pt_paths.GUI_SETTINGS_FILE
        if data and all(isinstance(v, dict) for v in data.values()):
            return pt_paths.EXCHANGE_CONFIG_FILE
    if data is not None:
        report.errors.append(
            (path, "unrecognised config file (expected pt_config, gui_settings, "
                   "trading_config or exchange_config)")
        )
    return None


def import_config_file(path: str, kind: Optional[str] = None) -> Report:
    """Import one config file from any location (e.g. a backup copied out of
    the repo). Same rules: credentials to the keyring, the rest to the config
    folder, nothing overwritten, nothing deleted."""
    report = Report()
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        report.errors.append((path, "file not found"))
        return report
    kind = kind or _detect_kind(path, report)
    if kind is None:
        return report
    state = _State()
    _migrate_config(path, kind, report, state, [os.path.dirname(path)])
    state.save()
    return report


# --- Robinhood ------------------------------------------------------------------------


def _migrate_robinhood(legacy: str, report: Report, state: _State) -> List[str]:
    """The old encrypted vault first, else the plaintext files. Returns the
    legacy files that are now redundant."""
    vault = [os.path.join(legacy, n) for n in RH_VAULT]
    plain = [os.path.join(legacy, n) for n in RH_PLAINTEXT]
    for files, label in ((vault, "vault"), (plain, "plain")):
        if not all(os.path.isfile(p) for p in files):
            continue
        source = files[0]
        key = f"secrets:robinhood:{label}"
        seen = state.entry(key, files[1])
        if seen is not None:
            if seen["redundant"]:
                return files + _robinhood_meta(legacy, report, state)
            continue
        creds = _read_robinhood(legacy, files, label, report)
        if creds is None:
            continue
        results = [
            _store_secret("robinhood", "api_key", creds[0], source, report),
            _store_secret("robinhood", "private_key", creds[1], source, report),
        ]
        if "error" in results:
            return []
        ok = "conflict" not in results
        state.mark(key, files[1], ok)
        return (files + _robinhood_meta(legacy, report, state)) if ok else []
    return []


def _read_robinhood(legacy: str, files: List[str], label: str, report: Report):
    if label == "vault":
        try:
            from pt_credentials import SecureCredentialManager

            creds = SecureCredentialManager(legacy).decrypt_credentials()
        except Exception as exc:  # cryptography missing, damaged vault, ...
            report.errors.append((files[0], f"old credential vault not readable ({type(exc).__name__})"))
            return None
        if not creds:
            report.errors.append(
                (files[0], "old credential vault could not be decrypted (it may come from "
                           "another computer); enter the Robinhood keys again in the setup wizard")
            )
        return creds
    try:
        values = []
        for p in files:
            with open(p, encoding="utf-8") as f:
                values.append(f.read().strip())
        return tuple(values) if all(values) else None
    except OSError as exc:
        report.errors.append((files[0], f"not readable ({type(exc).__name__})"))
        return None


def _robinhood_meta(legacy: str, report: Report, state: _State) -> List[str]:
    meta = os.path.join(legacy, RH_META)
    if os.path.isfile(meta) and _copy_file(
        meta, pt_paths.config_file("robinhood_rotation.json"), report, state
    ):
        return [meta]
    return []


# --- data -------------------------------------------------------------------------------


def _copy_tree(source_dir: str, target_dir: str, report: Report, state: _State,
               redirect: Optional[Dict[str, str]] = None) -> List[str]:
    """Copy every file under ``source_dir``; a first-level folder named in
    ``redirect`` goes to the folder given there instead."""
    redundant = []
    for folder, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel = os.path.relpath(folder, source_dir)
        top = rel.split(os.sep)[0] if rel != "." else ""
        base = target_dir
        if redirect and top in redirect:
            base = redirect[top]
            rel = os.path.relpath(folder, os.path.join(source_dir, top))
        for name in files:
            if name.endswith(".tmp"):
                continue
            src = os.path.join(folder, name)
            if _copy_file(src, os.path.normpath(os.path.join(base, rel, name)), report, state):
                redundant.append(src)
    return redundant


def _listdir(folder: str) -> List[str]:
    try:
        return sorted(os.listdir(folder))
    except OSError:
        return []


def _neural_files(folder: str) -> List[str]:
    return [
        os.path.join(folder, n)
        for n in _listdir(folder)
        if os.path.isfile(os.path.join(folder, n))
        and any(fnmatch.fnmatch(n, p) for p in NEURAL_PATTERNS)
    ]


def _coin_folders(legacy: str) -> List[str]:
    return [
        n for n in _listdir(legacy)
        if n.isupper() and n.isalnum() and len(n) <= 10 and os.path.isdir(os.path.join(legacy, n))
    ]


def _dest_dir(kind: str) -> str:
    return {"data": pt_paths.data_dir, "cache": pt_paths.cache_dir, "log": pt_paths.log_dir}[kind]()


# --- the run ----------------------------------------------------------------------------


def migrate(legacy_dir: Optional[str] = None, legacy_install_dir: Optional[str] = None,
            write_report: bool = True) -> Report:
    """Copy everything from the legacy folders that is not migrated yet."""
    legacy = os.path.abspath(legacy_dir or pt_paths.legacy_dir())
    root = os.path.abspath(legacy_install_dir or pt_paths.legacy_install_dir())
    report = Report()
    state = _State()
    redundant: List[str] = []

    # 1-2. config files and credentials
    for name in CONFIG_FILES:
        source = os.path.join(legacy, name)
        if os.path.isfile(source) and _migrate_config(source, name, report, state, (legacy, root)):
            redundant.append(source)
    redundant += _migrate_robinhood(legacy, report, state)
    stored_rh = pt_secrets.has_credentials("robinhood")
    for name in RH_PLAINTEXT:
        path = os.path.join(legacy, name)
        if os.path.isfile(path):
            report.plaintext_left.append(path)
    for pattern in RH_BACKUP_PATTERNS:  # old plaintext copies made by the Robinhood window
        for name in fnmatch.filter(_listdir(legacy), pattern):
            path = os.path.join(legacy, name)
            report.plaintext_left.append(path)
            if stored_rh:
                redundant.append(path)

    # 3. data: hub_data (candles are cache), neural files, databases, logs
    hub = os.path.join(legacy, pt_paths.HUB_DIR_NAME)
    if os.path.isdir(hub):
        redundant += _copy_tree(
            hub, pt_paths.hub_dir(), report, state,
            redirect={"candles": os.path.join(pt_paths.cache_dir(), "candles")},
        )
    neural_root = pt_paths.neural_dir()
    for src in _neural_files(legacy):
        if _copy_file(src, os.path.join(neural_root, os.path.basename(src)), report, state):
            redundant.append(src)
    for coin in _coin_folders(legacy):
        for src in _neural_files(os.path.join(legacy, coin)):
            if _copy_file(src, os.path.join(neural_root, coin, os.path.basename(src)), report, state):
                redundant.append(src)
    for base in dict.fromkeys((legacy, root)):
        for rel, kind, name in LOOSE_FILES:
            src = os.path.join(base, rel)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(_dest_dir(kind), name)
            if _copy_file(src, dst, report, state):
                redundant.append(src)
                for suffix in SQLITE_SIDECARS:
                    if os.path.isfile(src + suffix) and _copy_file(src + suffix, dst + suffix, report, state):
                        redundant.append(src + suffix)
        for name in fnmatch.filter(_listdir(base), "emergency_snapshot_*.json"):
            src = os.path.join(base, name)
            if _copy_file(src, os.path.join(pt_paths.log_dir(), name), report, state):
                redundant.append(src)
        logs = os.path.join(base, "logs")
        if os.path.isdir(logs):
            redundant += _copy_tree(logs, os.path.join(pt_paths.log_dir(), "legacy"), report, state)

    report.removable = sorted(dict.fromkeys(p for p in redundant if os.path.exists(p)))
    state.data["removable"] = report.removable
    state.save()
    if write_report and report.changed:
        report.report_path = write_report_file(report)
    return report


def write_report_file(report: Report) -> str:
    path = pt_paths.config_file(pt_paths.MIGRATION_REPORT_FILE)
    lines = [
        "# PowerTraderAI migration report",
        "",
        f"Run: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "Settings, data and credentials were moved out of the program folder (FDS-108a).",
        "No old file was changed or deleted.",
        "",
        "## Where things live now",
        "",
    ]
    for kind, folder in pt_paths.describe().items():
        lines.append(f"* {kind}: `{folder}`")
    lines.append("* credentials: the operating system's credential store (keyring)")
    sections = (
        ("Copied", [f"* `{s}` -> `{t}`" for s, t in report.copied]),
        ("Credentials moved to the OS keyring (field names only)",
         [f"* `{e}` (from `{s}`)" for s, e in report.secrets]),
        ("Conflicts (what was already in the new location was kept)",
         [f"* `{s}` was not copied; kept `{t}`" for s, t in report.conflicts]
         + [f"* `{e}` from `{s}` was not stored; the keyring already holds a different value"
            for s, e in report.secret_conflicts]),
        ("Not migrated", [f"* `{s}`: {m}" for s, m in report.errors]),
        ("Old files that still hold plaintext credentials",
         [f"* `{p}`" for p in dict.fromkeys(report.plaintext_left)]),
    )
    for title, items in sections:
        if items:
            lines += ["", f"## {title}", ""] + items
    if report.removable:
        lines += [
            "",
            "## Old copies that can be removed",
            "",
            "Use **Remove old files** in the migration window, or "
            "`python app/pt_migrate.py --remove-old-files`. " + PLAINTEXT_WARNING,
            "",
        ] + [f"* `{p}`" for p in report.removable]
    pt_paths.write_private_text(path, "\n".join(lines) + "\n")
    return path


def removable_legacy_files() -> List[str]:
    """Legacy copies the last migration run recorded as safe to delete."""
    try:
        with open(pt_paths.config_file(STATE_FILE), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [p for p in data.get("removable", []) if os.path.exists(p)]


def remove_legacy_files(paths: Optional[List[str]] = None, confirmed: bool = False) -> List[str]:
    """Delete migrated legacy copies. Does nothing unless ``confirmed`` is True,
    and only ever deletes files the migration recorded as safely copied."""
    if not confirmed:
        return []
    allowed = set(removable_legacy_files())
    targets = [p for p in (paths if paths is not None else sorted(allowed)) if p in allowed]
    removed = []
    for path in targets:
        try:
            os.remove(path)
            removed.append(path)
        except OSError as exc:
            logger.warning("Could not remove %s (%s)", path, type(exc).__name__)
    for folder in sorted({os.path.dirname(p) for p in removed}, key=len, reverse=True):
        _prune_empty(folder)
    return removed


def _prune_empty(folder: str) -> None:
    """Remove now-empty legacy data folders (hub_data/...), never a root folder."""
    roots = {
        os.path.normcase(os.path.abspath(p))
        for p in (pt_paths.legacy_dir(), pt_paths.legacy_install_dir(), pt_paths.program_dir())
    }
    while folder and os.path.isdir(folder) and not os.listdir(folder):
        if os.path.normcase(os.path.abspath(folder)) in roots:
            return
        try:
            os.rmdir(folder)
        except OSError:
            return
        folder = os.path.dirname(folder)


def run_startup_migration() -> Optional[Report]:
    """Hub start-up hook: migrate; return the report when something new
    happened, else None. Never raises: the hub must start regardless."""
    try:
        report = migrate()
    except Exception as exc:
        logger.error("Migration failed (%s): %s", type(exc).__name__, exc)
        return None
    return report if report.changed else None


def show_migration_dialog(parent, report: Report, messagebox=None):
    """A window summarising the report, with a **Remove old files** button that
    deletes the legacy copies only after the user confirms."""
    import tkinter as tk
    from tkinter import ttk

    if messagebox is None:
        from tkinter import messagebox

    win = tk.Toplevel(parent)
    win.title("PowerTraderAI: settings moved")
    try:
        win.transient(parent)
    except tk.TclError:
        pass
    text = (
        "PowerTraderAI now keeps your settings and data outside the program folder,\n"
        "and your API keys in the operating system's credential store.\n\n"
        + report.summary()
        + (f"\n\nFull report: {report.report_path}" if report.report_path else "")
    )
    ttk.Label(win, text=text, justify="left", wraplength=560).pack(padx=16, pady=(16, 8), anchor="w")
    buttons = ttk.Frame(win)
    buttons.pack(fill="x", padx=16, pady=(0, 16))

    def remove():
        files = removable_legacy_files()
        if not files:
            messagebox.showinfo("Nothing to remove", "There are no old copies left to remove.", parent=win)
            return
        listing = "\n".join(files[:15]) + ("\n..." if len(files) > 15 else "")
        if not messagebox.askyesno(
            "Remove old files?",
            f"Delete these {len(files)} old file(s) from the program folder?\n\n{listing}\n\n"
            + PLAINTEXT_WARNING,
            icon="warning",
            parent=win,
        ):
            return
        removed = remove_legacy_files(files, confirmed=True)
        messagebox.showinfo("Old files removed", f"Removed {len(removed)} file(s).", parent=win)
        remove_button.state(["disabled"])

    remove_button = ttk.Button(buttons, text="Remove old files", command=remove)
    remove_button.pack(side="left")
    if not report.removable:
        remove_button.state(["disabled"])
    ttk.Button(buttons, text="Close", command=win.destroy).pack(side="right")
    win.remove_button = remove_button
    win.remove_old_files = remove
    return win


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Move PowerTraderAI settings, data and credentials out of the program folder."
    )
    parser.add_argument("--from", dest="source", metavar="PATH",
                        help="import one config file from any location")
    parser.add_argument("--remove-old-files", action="store_true",
                        help="delete migrated legacy copies (asks first)")
    parser.add_argument("--yes", action="store_true", help="with --remove-old-files: do not ask")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.remove_old_files:
        files = removable_legacy_files()
        if not files:
            print("No migrated legacy copies to remove.")
            return 0
        print("\n".join(files))
        print(PLAINTEXT_WARNING)
        if not args.yes and input(f"Delete these {len(files)} file(s)? Type 'yes': ").strip().lower() != "yes":
            print("Nothing deleted.")
            return 1
        print(f"Removed {len(remove_legacy_files(files, confirmed=True))} file(s).")
        return 0

    report = import_config_file(args.source) if args.source else migrate()
    if args.source and report.changed:
        report.report_path = write_report_file(report)
    print(report.summary())
    if report.report_path:
        print(f"Report: {report.report_path}")
    for source, message in report.errors:
        print(f"  not migrated: {source}: {message}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
