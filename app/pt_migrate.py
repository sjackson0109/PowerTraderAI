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
  ``remove_old_files`` deletes migrated legacy copies only when called with
  ``confirmed=True`` (the hub asks first and warns that they may hold
  plaintext credentials). A legacy file whose content was not migrated (a
  conflict, or a credential that could not be stored) is never offered.
* Before deleting, every legacy file is checked again against the migration
  record: it must be recorded as migrated and safe to remove, its SHA-256 must
  still be the one recorded when it was migrated, and its migrated copy (a
  file, or a keyring entry for a credential) must still exist and must not be
  the file itself. A file that fails a check is kept and reported with the
  reason. The check is repeated once the file is renamed aside, just before
  it is deleted, so a write that lands in between keeps it. A SQLite database
  and its ``-wal``/``-shm``/``-journal`` files are one unit: compared, copied,
  checked and deleted together, all or none. The copy of each part is the
  migrated database; a ``-wal`` or ``-journal`` that holds data counts as
  migrated only while its own copy is there, or once SQLite has merged (or
  rolled back) it into the migrated database (which then differs from what
  was copied). A read-only part keeps the whole unit before anything is
  renamed; if a delete still fails, the parts not yet deleted are put back
  (the database goes last, so a ``-wal`` or ``-journal`` is never left
  without it) and are reported as not removed. In a git checkout
  ``app/pt_config.json`` and ``app/gui_settings.json`` are always kept: other
  branches still use them. That is decided from where the file is (and
  recorded at migration), not from where this program runs.
* A file in a folder PowerTrader uses now (``POWERTRADER_HOME`` may be the
  install root or ``app/``, whose ``data/`` and ``logs/`` are also legacy
  locations) is the new app's own file: never copied, recorded or removed.
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
import functools
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
# A database in WAL mode has -wal/-shm files; one in rollback mode a -journal,
# which after a crash mid-commit ("hot") holds the last committed pages.
SQLITE_SIDECARS = ("-wal", "-shm", "-journal")
# Sidecars that can hold data the .db does not have yet.
SQLITE_DATA_SIDECARS = ("-wal", "-journal")

# Robinhood legacy files.
RH_PLAINTEXT = ("r_key.txt", "r_secret.txt")
RH_VAULT = ("r_key.enc", "r_secret.enc", ".pt_salt")
RH_META = ".pt_cred_meta"
RH_BACKUP_PATTERNS = ("r_key.txt.bak_*", "r_secret.txt.bak_*")

# A migrated credential's copy, as the migration record names it.
KEYRING_COPY = "keyring:"
RH_COPIES = (KEYRING_COPY + "robinhood:api_key", KEYRING_COPY + "robinhood:private_key")

# Why Remove old files leaves a legacy file in place.
NOT_MIGRATED = "not part of the migration"
CHANGED = "changed since it was migrated"
NO_COPY = "no migrated copy"
IN_USE = "in a folder PowerTrader uses now"
LINKED = "reached through a link or junction since it was migrated"
KEPT_FOR_BRANCHES = "kept: other branches in this git checkout still use it"
REMOVING_SUFFIX = ".pt-removing"  # a part renamed aside while its unit is deleted

# Legacy settings that other branches of a git checkout still read from app/.
BRANCH_SETTINGS = (pt_paths.SETTINGS_FILE, pt_paths.GUI_SETTINGS_FILE)

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


@dataclass
class Removal:
    """What **Remove old files** found, or did, per legacy file."""

    removable: List[str] = field(default_factory=list)  # passed every check
    removed: List[str] = field(default_factory=list)  # deleted (only when confirmed)
    refused: List[Tuple[str, str]] = field(default_factory=list)  # (legacy file, reason)
    kept: List[Tuple[str, str]] = field(default_factory=list)  # (legacy file, reason)

    def not_removed(self) -> List[str]:
        return [f"{path}: {reason}" for path, reason in self.refused + self.kept]


# --- state ------------------------------------------------------------------------


def _fingerprint(paths) -> list:
    """``[size, mtime_ns]`` of a file. For a list of paths (a database and its
    -wal/-shm/-journal files) one such pair per path, None where the file is absent."""
    if isinstance(paths, str):
        st = os.stat(paths)
        return [st.st_size, st.st_mtime_ns]
    return [_fingerprint(p) if os.path.isfile(p) else None for p in paths]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class _State:
    """``migration-state.json``::

        {"items": {key: {"fp": fingerprint, "redundant": bool}},
         "files": {legacy file: {"fp": [size, mtime_ns], "sha256": hex, "copy": [location, ...],
                                 "keep": true (only when set)}},
         "removable": [[legacy file, ...], ...]}

    ``items`` makes a run idempotent. ``files`` and ``removable`` are the
    record that **Remove old files** checks: for each migrated legacy file the
    SHA-256 of the content that was migrated and where its copy is (a path, or
    ``keyring:<exchange>:<field>``), and the legacy files that are safe to
    delete, in units (a database with its -wal/-shm/-journal files is one unit).
    ``keep`` marks settings migrated from a git checkout (never removed).
    """

    def __init__(self):
        self.path = pt_paths.config_file(STATE_FILE)
        self.data = {"items": {}, "files": {}, "removable": []}
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and isinstance(loaded.get("items"), dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass
        if not isinstance(self.data.get("files"), dict):
            self.data["files"] = {}
        self._original = json.dumps(self.data, sort_keys=True)

    def entry(self, key: str, source) -> Optional[dict]:
        """The record for ``key`` if the legacy file (or unit) has not changed since."""
        item = self.data["items"].get(key)
        try:
            if item and item.get("fp") == _fingerprint(source):
                return item
        except OSError:
            pass
        return None

    def mark(self, key: str, source, redundant: bool) -> None:
        try:
            self.data["items"][key] = {"fp": _fingerprint(source), "redundant": bool(redundant)}
        except OSError:
            pass

    def remember(self, path: str, copies: Iterable[str], sha256: Optional[str] = None,
                 keep: bool = False) -> None:
        """Record a migrated legacy file: its SHA-256 (``sha256``, else read now),
        its real path (links resolved) and where its copy is; ``keep`` marks it
        as never to be removed (a mark once set stays). The record of an
        unchanged file is kept, so its hash and real path stay the ones taken
        when it was migrated."""
        copies = list(copies)
        try:
            fp = _fingerprint(path)
            record = self.data["files"].get(path)
            keep = keep or (isinstance(record, dict) and bool(record.get("keep")))
            if not (
                isinstance(record, dict) and record.get("fp") == fp and record.get("copy") == copies
                and record.get("sha256")
            ):
                record = self.data["files"][path] = {
                    "fp": fp, "sha256": sha256 or _sha256(path), "copy": copies, "real": _real(path),
                }
            if keep:
                record["keep"] = True
        except OSError:
            pass

    def units(self) -> List[List[str]]:
        """The removable units (an older record without units yields none)."""
        return [
            unit for unit in self.data.get("removable") or []
            if isinstance(unit, list) and unit and all(isinstance(p, str) for p in unit)
        ]

    def save(self) -> None:
        listed = {p for unit in self.units() for p in unit}
        self.data["files"] = {p: r for p, r in self.data["files"].items() if p in listed}
        if json.dumps(self.data, sort_keys=True) != self._original:
            pt_paths.write_private_text(self.path, json.dumps(self.data, indent=2, sort_keys=True))


# --- helpers ------------------------------------------------------------------------


def _same_unit(pairs: List[Tuple[str, str]]) -> Optional[Dict[str, str]]:
    """The SHA-256 of each legacy part when the target holds exactly the same
    parts with the same content (for a database: the .db, -wal, -shm and
    -journal files), else None."""
    digests = {}
    for source, target in pairs:
        if os.path.isfile(source) != os.path.exists(target):
            return None
        if not os.path.isfile(source):
            continue
        if os.path.getsize(source) != os.path.getsize(target):
            return None
        digest = _sha256(source)
        if digest != _sha256(target):
            return None
        digests[source] = digest
    return digests


def _copy_parts(pairs: List[Tuple[str, str]]) -> Dict[str, str]:
    """Copy every part (no target exists yet). On a failure the parts copied so
    far are removed again and the error is raised. Returns the SHA-256 of each
    copy, by legacy part."""
    try:
        for source, target in pairs:
            pt_paths.make_private_dir(os.path.dirname(target))
            shutil.copy2(source, target)
    except OSError:
        for _, target in pairs:
            try:
                os.remove(target)
            except OSError:
                pass
        raise
    return {source: _sha256(target) for source, target in pairs}


def _copy_file(source: str, target: str, report: Report, state: _State) -> List[str]:
    """Copy one file, never overwriting. A database comes with its
    -wal/-shm/-journal files as one unit: compared, copied and recorded together. Returns the
    legacy parts when they are redundant (copied now or earlier, or already
    identical at the target), else [].

    Each part is recorded with the SHA-256 of what was copied and with
    ``target`` as its copy: SQLite merges and deletes the -wal/-shm files of
    the migrated database when it closes it (and rolls back and deletes a hot
    -journal when it opens it), so the .db is what must remain. Until then, a
    -wal or -journal with data also needs its own copy (``_refusal``).

    A source in a folder PowerTrader uses now, or that is its own target, is
    the new app's own file: skipped, never recorded as its own copy. (With
    ``POWERTRADER_HOME`` at the install root, ``logs/`` is the log folder:
    copying it into ``logs/legacy`` would nest it deeper on every run.)"""
    pairs = [(source + s, target + s) for s in ("",) + SQLITE_SIDECARS]
    if _in_new_location(source) or any(os.path.isfile(s) and _same_file(s, t) for s, t in pairs):
        return []
    sources = [s for s, _ in pairs]
    key = f"file:{source}"
    seen = state.entry(key, sources)
    if seen is not None:
        if seen["redundant"] and os.path.exists(target):
            return [s for s in sources if os.path.isfile(s)]
        return []
    present = [(s, t) for s, t in pairs if os.path.isfile(s)]
    try:
        if any(os.path.exists(t) for _, t in pairs):
            digests = _same_unit(pairs)
            if digests is None:
                report.conflicts.append((source, target))
                state.mark(key, sources, False)
                return []
        else:
            digests = _copy_parts(present)
            report.copied += present
    except OSError as exc:
        report.errors.append((source, f"copy failed ({type(exc).__name__})"))
        return []
    for part, _ in present:
        state.remember(part, [target], digests[part])
    state.mark(key, sources, True)
    return [s for s, _ in present]


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


def _read_json(path: str, report: Report) -> Tuple[object, Optional[str]]:
    """The parsed file and the SHA-256 of the bytes it was parsed from."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError) as exc:
        report.errors.append((path, f"not readable as JSON ({type(exc).__name__})"))
        return None, None


def _load_json(path: str, report: Report):
    return _read_json(path, report)[0]


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


def _credential_items(source: str, pairs, report: Report) -> Tuple[List[Tuple[str, str, str]], bool]:
    """``(exchange, field, value)`` per credential, and whether every credential
    has a keyring field (one that has not stays only in the legacy file)."""
    items = []
    complete = True
    for exchange, key, value in pairs:
        value = str(value or "").strip()
        if not value:
            continue
        field_name = _secret_field(exchange, key) if exchange else None
        if field_name:
            items.append((exchange, field_name, value))
        else:
            complete = False
            report.errors.append((source, f"{exchange or '?'}.{key}: no keyring field for it, not moved"))
    return items, complete


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


def _real(path: str) -> str:
    """``path`` with links, junctions, subst drives and short names resolved."""
    return os.path.normcase(os.path.realpath(path))


def _linked(path: str) -> bool:
    """Whether ``path`` is a symbolic link or (Windows) a junction."""
    return os.path.islink(path) or bool(getattr(os.path, "isjunction", lambda p: False)(path))


def _through_link(path: str, top: str) -> bool:
    """Whether ``path``, or a folder between ``top`` and it (``top`` itself
    not included), is a link or junction: what it names lives elsewhere, maybe
    outside every legacy folder, so it is neither copied nor ever removed."""
    top = os.path.normcase(os.path.abspath(top))
    path = os.path.abspath(path)
    while os.path.normcase(path) != top:
        if _linked(path):
            return True
        parent = os.path.dirname(path)
        if parent == path:
            return False
        path = parent
    return False


def _same_file(a: str, b: str) -> bool:
    """Whether two existing paths name the same file, however each is spelled."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


@functools.lru_cache(maxsize=16)
def _resolved(folders: Tuple[str, ...]) -> Tuple[str, ...]:
    """``_real`` of each folder, once (resolving a path is slow on Windows)."""
    return tuple(_real(f) for f in folders)


def _in_new_location(path: str) -> bool:
    """Whether ``path`` is in a folder PowerTrader uses now (config, data, logs,
    cache), however it is spelled. With ``POWERTRADER_HOME`` at the install
    root or in ``app/`` its ``data/`` and ``logs/`` are also legacy locations."""
    folders = _resolved((
        pt_paths.config_dir(create=False), pt_paths.data_dir(create=False),
        pt_paths.log_dir(create=False), pt_paths.cache_dir(create=False),
    ))
    path = _real(path)
    return any(_inside(path, folder) for folder in folders)


def _git_checkout(folder: str) -> bool:
    """A ``.git`` folder, or a ``.git`` file (worktree, submodule), in ``folder``."""
    return os.path.exists(os.path.join(folder, ".git"))


def _copy_exists(location: str) -> bool:
    """Whether a recorded migrated copy is still there: a file, or a keyring
    entry ``keyring:<exchange>:<field>`` (checked by name)."""
    if location.startswith(KEYRING_COPY):
        exchange, _, name = location[len(KEYRING_COPY):].partition(":")
        try:
            return name in pt_secrets.stored_fields(exchange)
        except pt_secrets.SecretsError:
            return False
    return os.path.isfile(location)


# --- config files ---------------------------------------------------------------------


def _migrate_config(source: str, kind: str, report: Report, state: _State,
                    legacy_roots: Iterable[str], keep: bool = False) -> bool:
    """One legacy config file: credentials to the keyring, the rest to the
    config folder. True when the legacy file is now redundant; it is then
    recorded with the SHA-256 that was read and its copies (the config file
    and the keyring entries), and with ``keep`` (never removed)."""
    data, digest = _read_json(source, report)
    if not isinstance(data, (dict, list)):
        return False
    pairs = None
    if kind == pt_paths.TRADING_CONFIG_FILE and isinstance(data, dict):
        pairs = [
            (str(ex.get("exchange_type", "")).strip().lower(), key, ex.get(key))
            for ex in data.get("exchanges", []) or []
            if isinstance(ex, dict)
            for key in ("api_key", "api_secret", "passphrase")
        ]
    elif kind == pt_paths.EXCHANGE_CONFIG_FILE and isinstance(data, dict):
        pairs = [
            (str(name).strip().lower(), key, value)
            for name, settings in data.items()
            if isinstance(settings, dict)
            for key, value in settings.items()
            if pt_secrets.is_secret_key(key)
        ]
    items: List[Tuple[str, str, str]] = []
    secrets_ok = True
    if pairs is not None:
        items, complete = _credential_items(source, pairs, report)
        secrets_ok = _migrate_secrets(source, items, report, state) and complete
    clean = pt_secrets.strip_secret_fields(data, os.path.basename(source), warn=False)
    if kind == pt_paths.GUI_SETTINGS_FILE and isinstance(clean, dict):
        clean = _relocated_gui_settings(clean, legacy_roots)
    target = pt_paths.config_file(kind)
    written = _write_config(source, target, clean, report, state)
    if _holds_secret(data):
        report.plaintext_left.append(source)
    if not (written and secrets_ok):
        return False
    state.remember(source, [target] + [f"{KEYRING_COPY}{ex}:{f}" for ex, f, _ in items], digest, keep)
    return True


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


def _migrate_robinhood(legacy: str, report: Report, state: _State) -> List[List[str]]:
    """The old encrypted vault first, else the plaintext files. Returns the
    legacy files that are now redundant, as units."""
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
                return [[p] for p in files] + _robinhood_meta(legacy, report, state)
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
        if not ok:
            return []
        for path in files:
            state.remember(path, RH_COPIES)
        return [[p] for p in files] + _robinhood_meta(legacy, report, state)
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


def _robinhood_meta(legacy: str, report: Report, state: _State) -> List[List[str]]:
    meta = os.path.join(legacy, RH_META)
    if not os.path.isfile(meta):
        return []
    return [_copy_file(meta, pt_paths.config_file("robinhood_rotation.json"), report, state)]


# --- data -------------------------------------------------------------------------------


def _copy_tree(source_dir: str, target_dir: str, report: Report, state: _State,
               redirect: Optional[Dict[str, str]] = None) -> List[List[str]]:
    """Copy every file under ``source_dir`` (a database with its
    -wal/-shm/-journal files as one unit); a first-level folder named in
    ``redirect`` goes to the folder given there instead. Returns the
    redundant legacy units. Links and junctions are not followed
    (``_through_link``): ``os.walk`` follows a junction on Windows."""
    units = []
    for folder, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__" and not _linked(os.path.join(folder, d))]
        rel = os.path.relpath(folder, source_dir)
        top = rel.split(os.sep)[0] if rel != "." else ""
        base = target_dir
        if redirect and top in redirect:
            base = redirect[top]
            rel = os.path.relpath(folder, os.path.join(source_dir, top))
        names = set(files)
        for name in files:
            if name.endswith(".tmp") or _linked(os.path.join(folder, name)):
                continue
            if any(name.endswith(s) and name[: -len(s)] in names for s in SQLITE_SIDECARS):
                continue  # copied with its database
            src = os.path.join(folder, name)
            units.append(_copy_file(src, os.path.normpath(os.path.join(base, rel, name)), report, state))
    return units


def _listdir(folder: str) -> List[str]:
    try:
        return sorted(os.listdir(folder))
    except OSError:
        return []


def _neural_files(folder: str) -> List[str]:
    return [
        os.path.join(folder, n)
        for n in _listdir(folder)
        if os.path.isfile(os.path.join(folder, n)) and not _linked(os.path.join(folder, n))
        and any(fnmatch.fnmatch(n, p) for p in NEURAL_PATTERNS)
    ]


def _coin_folders(legacy: str) -> List[str]:
    return [
        n for n in _listdir(legacy)
        if n.isupper() and n.isalnum() and len(n) <= 10 and os.path.isdir(os.path.join(legacy, n))
        and not _linked(os.path.join(legacy, n))
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
    units: List[List[str]] = []  # redundant legacy files; a database with its sidecars is one unit

    # 1-2. config files and credentials; in a git checkout the settings other
    # branches read are recorded as kept, so a later run from elsewhere keeps them too
    checkout = _git_checkout(root) or _git_checkout(os.path.dirname(legacy))
    for name in CONFIG_FILES:
        source = os.path.join(legacy, name)
        if os.path.isfile(source) and _migrate_config(
            source, name, report, state, (legacy, root), keep=checkout and name in BRANCH_SETTINGS
        ):
            units.append([source])
    units += _migrate_robinhood(legacy, report, state)
    stored_rh = all(_copy_exists(c) for c in RH_COPIES)
    for name in RH_PLAINTEXT:
        path = os.path.join(legacy, name)
        if os.path.isfile(path):
            report.plaintext_left.append(path)
    for pattern in RH_BACKUP_PATTERNS:  # old plaintext copies made by the Robinhood window
        for name in fnmatch.filter(_listdir(legacy), pattern):
            path = os.path.join(legacy, name)
            report.plaintext_left.append(path)
            if stored_rh:
                state.remember(path, RH_COPIES)
                units.append([path])

    # 3. data: hub_data (candles are cache), neural files, databases, logs
    hub = os.path.join(legacy, pt_paths.HUB_DIR_NAME)
    if os.path.isdir(hub) and not _through_link(hub, legacy):
        units += _copy_tree(
            hub, pt_paths.hub_dir(), report, state,
            redirect={"candles": os.path.join(pt_paths.cache_dir(), "candles")},
        )
    neural_root = pt_paths.neural_dir()
    for src in _neural_files(legacy):
        units.append(_copy_file(src, os.path.join(neural_root, os.path.basename(src)), report, state))
    for coin in _coin_folders(legacy):
        for src in _neural_files(os.path.join(legacy, coin)):
            units.append(
                _copy_file(src, os.path.join(neural_root, coin, os.path.basename(src)), report, state)
            )
    for base in dict.fromkeys((legacy, root)):
        for rel, kind, name in LOOSE_FILES:
            src = os.path.join(base, rel)
            if os.path.isfile(src) and not _through_link(src, base):
                units.append(_copy_file(src, os.path.join(_dest_dir(kind), name), report, state))
        for name in fnmatch.filter(_listdir(base), "emergency_snapshot_*.json"):
            src = os.path.join(base, name)
            if not _linked(src):
                units.append(_copy_file(src, os.path.join(pt_paths.log_dir(), name), report, state))
        logs = os.path.join(base, "logs")
        if os.path.isdir(logs) and not _through_link(logs, base):
            units += _copy_tree(logs, os.path.join(pt_paths.log_dir(), "legacy"), report, state)

    # Safe to remove: every part of the unit exists and is recorded (hash and copy).
    recorded = state.data["files"]
    units = sorted({
        tuple(unit) for unit in units
        if unit and all(os.path.exists(p) and p in recorded for p in unit)
    })
    state.data["removable"] = [list(unit) for unit in units]
    report.removable = sorted({p for unit in units for p in unit})
    state.save()
    if write_report and report.changed:
        report.report_path = write_report_file(report, state.data["files"])
    return report


def write_report_file(report: Report, records: Optional[Dict[str, dict]] = None) -> str:
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
            "`python app/pt_migrate.py --remove-old-files`. Each file is checked again first; "
            "one that changed since it was migrated, or whose migrated copy is gone, is kept. "
            + PLAINTEXT_WARNING,
            "",
        ]
        for p in report.removable:
            kept = _kept_reason(p, (records or {}).get(p))
            lines.append(f"* `{p}`" + (f" ({kept})" if kept else ""))
    pt_paths.write_private_text(path, "\n".join(lines) + "\n")
    return path


# --- removing old files -------------------------------------------------------------------


def _kept_reason(path: str, record: Optional[dict] = None) -> Optional[str]:
    """In a git checkout other branches still read the old ``app/pt_config.json``
    and ``app/gui_settings.json``, so those are never removed there. Decided
    from the file itself, not from where this program runs (the record is per
    user, so it can list another checkout's files): its record says ``keep``
    (its install root was a checkout when it was migrated), or its install
    root is a checkout now. That root is the folder above the file's own, or
    ``legacy_install_dir()`` for this program's legacy settings, compared as
    the same file however the path is spelled."""
    name = os.path.basename(path)
    if os.path.normcase(name) not in BRANCH_SETTINGS:
        return None
    roots = [os.path.dirname(os.path.dirname(os.path.abspath(path)))]
    if _same_file(path, os.path.join(pt_paths.legacy_dir(), name)):
        roots.append(pt_paths.legacy_install_dir())
    if (isinstance(record, dict) and record.get("keep")) or any(_git_checkout(r) for r in roots):
        return KEPT_FOR_BRANCHES
    return None


def _valid_record(record) -> bool:
    return (
        isinstance(record, dict)
        and isinstance(record.get("sha256"), str) and len(record["sha256"]) == 64
        and isinstance(record.get("copy"), list) and bool(record["copy"])
        and all(isinstance(c, str) and c for c in record["copy"])
    )


def _refusal(unit: List[str], files: Dict[str, dict], suffix: str = "") -> Optional[str]:
    """Why ``unit`` must not be deleted now, or None. Every part must be
    (1) recorded as migrated, with a hash and a copy, and not in a folder
    PowerTrader uses now, (2) unchanged: the SHA-256 recorded at migration,
    and no sidecar file the unit did not have, (3) still migrated: its copy
    exists and is not the part itself; and its real path is still the one
    recorded (no link or junction on its way now). ``suffix``: each part is read under
    its name plus ``suffix`` (renamed aside by ``_delete_unit``)."""
    records = [files.get(p) for p in unit]
    if not all(_valid_record(r) for r in records):
        return NOT_MIGRATED
    if any(_in_new_location(p) for p in unit):
        return IN_USE
    if any(
        r.get("real") and _real(p + suffix) != r["real"] + os.path.normcase(suffix)
        for p, r in zip(unit, records)
    ):
        return LINKED  # a folder on its path became a link: the file lives elsewhere now
    if any(os.path.isfile(unit[0] + s) and unit[0] + s not in unit for s in SQLITE_SIDECARS):
        return CHANGED
    for path, record in zip(unit, records):
        if not os.path.isfile(path + suffix):
            return CHANGED
        try:
            if _sha256(path + suffix) != record["sha256"]:
                return CHANGED
        except OSError as exc:
            return f"could not be read ({type(exc).__name__})"
    copies = [c for r in records for c in r["copy"]]
    if not all(_copy_exists(c) for c in copies) or any(
        _same_file(c, p + suffix) for c in copies if not c.startswith(KEYRING_COPY) for p in unit
    ):
        return NO_COPY
    for side in SQLITE_DATA_SIDECARS:
        # The copy of a -wal (or hot -journal) is the migrated .db, which holds
        # what it held only once SQLite merged (or rolled back) it: the .db then
        # changed. One with data whose own copy is gone, next to a migrated .db
        # still as copied, was never applied there: its content is nowhere else.
        part = unit[0] + side
        if part not in unit:
            continue
        target = files[part]["copy"][0]
        try:
            if (
                os.path.getsize(part + suffix)
                and not os.path.isfile(target + side)
                and _sha256(target) == files[unit[0]]["sha256"]
            ):
                return NO_COPY
        except OSError as exc:
            return f"could not be read ({type(exc).__name__})"
    return None


def _cannot_delete(unit: List[str]) -> Optional[str]:
    """Why a part of ``unit`` cannot be deleted, found before anything is
    renamed: it is read-only (Windows renames such a file but will not delete
    it), or a ``.pt-removing`` file is in its way (left by an earlier removal
    with content it could not put back, which a rename would replace)."""
    for path in unit:
        if os.path.lexists(path + REMOVING_SUFFIX):
            return f"could not be removed ({os.path.basename(path)}{REMOVING_SUFFIX} is in the way)"
        if not os.access(path, os.W_OK):
            return "could not be removed (read-only)"
    return None


def _restore(aside: List[str]) -> List[str]:
    """Put parts renamed aside back under their names, never over a file that
    appeared there meanwhile. Returns the parts left renamed aside (logged)."""
    left = []
    for path in reversed(aside):
        if not os.path.lexists(path):
            try:
                os.rename(path + REMOVING_SUFFIX, path)
                continue
            except OSError:
                pass
        logger.warning("Could not restore %s (left as %s)", path, path + REMOVING_SUFFIX)
        left.append(path)
    return left


def _put_back(unit: List[str], aside: List[str], reason: str) -> List[Tuple[str, str]]:
    """Restore the parts in ``aside`` and refuse every part of ``unit`` with
    ``reason``, naming the file a part was left as if it could not go back."""
    left = _restore(aside)
    return [
        (p, f"{reason}, left as {os.path.basename(p)}{REMOVING_SUFFIX}" if p in left else reason)
        for p in unit
    ]


def _delete_unit(unit: List[str], files: Dict[str, dict]) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Delete all parts or none. A part that cannot be deleted
    (``_cannot_delete``) stops the unit before anything is touched. Each part
    is then renamed aside, so a part that cannot go (a database another
    program holds open, ...) stops the unit before anything is deleted. Then
    the unit is checked again as renamed (``_refusal``), and nothing may have
    appeared under its names (a new sidecar file, or a part written again): a
    write that landed after the first check puts every part back, refused. On
    Windows no program can write to a part once it is renamed (one holding it
    open makes the rename fail), so what is deleted is what was checked.

    The sidecar files are deleted before the .db. If a delete still fails
    (something opened the part after the rename), the parts not yet deleted
    are put back and refused; those already deleted stay deleted (each passed
    every check). What stays is then a database, never a -wal or -journal
    without one.
    Returns the parts deleted, and each part kept with the reason."""
    reason = _cannot_delete(unit)
    if reason is not None:
        return [], [(p, reason) for p in unit]
    aside: List[str] = []
    for path in unit:
        try:
            os.rename(path, path + REMOVING_SUFFIX)
        except OSError as exc:
            return [], _put_back(unit, aside, f"could not be removed ({type(exc).__name__})")
        aside.append(path)
    names = set(unit) | {unit[0] + s for s in SQLITE_SIDECARS}
    reason = (
        CHANGED if any(os.path.lexists(n) for n in names)
        else _refusal(unit, files, REMOVING_SUFFIX)
    )
    if reason is not None:
        return [], _put_back(unit, aside, reason)
    deleted = set()
    for path in reversed(unit):
        try:
            os.remove(path + REMOVING_SUFFIX)
        except OSError as exc:
            kept = [p for p in unit if p not in deleted]
            return (
                [p for p in unit if p in deleted],
                _put_back(kept, kept, f"could not be removed ({type(exc).__name__})"),
            )
        deleted.add(path)
    return list(unit), []


def remove_old_files(paths: Optional[List[str]] = None, confirmed: bool = False) -> Removal:
    """The one code path behind **Remove old files** (the hub dialog and
    ``--remove-old-files``). Each legacy file is checked against the migration
    record (``_refusal``); a file that fails is refused with the reason, and
    in a git checkout ``pt_config.json`` and ``gui_settings.json`` are kept.

    ``paths`` None means every file the record marks removable; a path that is
    part of a database unit selects the whole unit. Without ``confirmed``
    nothing is deleted and the result says what would be (a part that could
    not be deleted is refused here too). With it, each unit is checked again
    immediately before it is deleted, and once more after it is renamed aside
    (``_delete_unit``), all parts or none; only what was deleted is reported
    as removed."""
    state = _State()
    files = state.data["files"]
    units = state.units()
    unit_of = {_real(p): unit for unit in units for p in unit}
    if paths is None:
        paths = [p for unit in units for p in unit]
    result = Removal()
    handled = set()
    for path in paths:
        unit = unit_of.get(_real(path))
        parts = unit or [path]
        key = tuple(_real(p) for p in parts)
        if key in handled:
            continue
        handled.add(key)
        present = [p for p in parts if os.path.exists(p)]
        if not present:
            continue  # already gone
        reason = _kept_reason(parts[0], files.get(parts[0]))
        if reason:
            result.kept += [(p, reason) for p in present]
            continue
        reason = _refusal(unit, files) if unit else NOT_MIGRATED
        if reason is None and not confirmed:
            reason = _cannot_delete(unit)  # what _delete_unit would find first
        if reason is not None:
            result.refused += [(p, reason) for p in present]
        elif not confirmed:
            result.removable += unit
        else:
            deleted, refused = _delete_unit(unit, files)
            result.removable += deleted
            result.removed += deleted
            result.refused += refused
    for folder in sorted({os.path.dirname(p) for p in result.removed}, key=len, reverse=True):
        _prune_empty(folder)
    return result


def removable_legacy_files() -> List[str]:
    """Legacy copies that pass every check of ``remove_old_files`` now."""
    return remove_old_files().removable


def remove_legacy_files(paths: Optional[List[str]] = None, confirmed: bool = False) -> List[str]:
    """Delete migrated legacy copies through ``remove_old_files``; returns the
    deleted files. Does nothing unless ``confirmed`` is True."""
    if not confirmed:
        return []
    return remove_old_files(paths, confirmed=True).removed


def _prune_empty(folder: str) -> None:
    """Remove now-empty legacy data folders (hub_data/...), never a root folder
    (however its path is spelled) and never a link or junction."""
    roots = {
        _real(p) for p in (pt_paths.legacy_dir(), pt_paths.legacy_install_dir(), pt_paths.program_dir())
    }
    while folder and os.path.isdir(folder) and not os.listdir(folder):
        if _real(folder) in roots or _linked(folder):
            return
        try:
            os.rmdir(folder)
        except OSError:
            return
        folder = os.path.dirname(folder)


def _not_removed_text(*results: Removal, limit: int = 15) -> str:
    """The files left in place, with the reason, for the dialog ('' if none)."""
    lines = [line for result in results for line in result.not_removed()]
    if not lines:
        return ""
    return "\n\nNot removed:\n" + "\n".join(lines[:limit] + (["..."] if len(lines) > limit else []))


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
    deletes the legacy copies only after the user confirms (``remove_old_files``
    checks every file again and lists those it keeps, with the reason)."""
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
        check = remove_old_files()
        files = check.removable
        if not files:
            messagebox.showinfo(
                "Nothing to remove",
                "There are no old copies left to remove." + _not_removed_text(check),
                parent=win,
            )
            return
        listing = "\n".join(files[:15]) + ("\n..." if len(files) > 15 else "")
        if not messagebox.askyesno(
            "Remove old files?",
            f"Delete these {len(files)} old file(s) from the program folder?\n\n{listing}"
            + _not_removed_text(check) + "\n\n" + PLAINTEXT_WARNING,
            icon="warning",
            parent=win,
        ):
            return
        done = remove_old_files(files, confirmed=True)
        messagebox.showinfo(
            "Old files removed",
            f"Removed {len(done.removed)} file(s)." + _not_removed_text(check, done),
            parent=win,
        )
        remove_button.state(["disabled"])

    remove_button = ttk.Button(buttons, text="Remove old files", command=remove)
    remove_button.pack(side="left")
    if not report.removable:
        remove_button.state(["disabled"])
    ttk.Button(buttons, text="Close", command=win.destroy).pack(side="right")
    win.remove_button = remove_button
    win.remove_old_files = remove
    return win


def _print_not_removed(result: Removal) -> None:
    for line in result.not_removed():
        print(f"  not removed: {line}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Move PowerTraderAI settings, data and credentials out of the program folder."
    )
    parser.add_argument("--from", dest="source", metavar="PATH",
                        help="import one config file from any location")
    parser.add_argument("--remove-old-files", action="store_true",
                        help="delete migrated legacy copies that are unchanged and still "
                             "have their migrated copy (asks first)")
    parser.add_argument("--yes", action="store_true", help="with --remove-old-files: do not ask")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.remove_old_files:
        check = remove_old_files()
        files = check.removable
        if not files:
            print("No migrated legacy copies to remove.")
            _print_not_removed(check)
            return 1 if check.refused else 0
        print("\n".join(files))
        _print_not_removed(check)
        print(PLAINTEXT_WARNING)
        if not args.yes and input(f"Delete these {len(files)} file(s)? Type 'yes': ").strip().lower() != "yes":
            print("Nothing deleted.")
            return 1
        done = remove_old_files(files, confirmed=True)
        print(f"Removed {len(done.removed)} file(s).")
        _print_not_removed(done)
        return 1 if check.refused or done.refused else 0

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
