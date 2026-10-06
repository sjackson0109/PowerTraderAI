"""Published model artifacts with provenance (FDS-MDL Phase 2; addendum section 4.1).

Every pattern-trainer run publishes the model it wrote into
``pt_paths.strategy_models_dir() / <model_id> /``: a copy of the 35 model files plus
``manifest.json``, which records where the model came from (trainer, window, data,
seed, validation metrics) and the SHA-256 of every file. The trainer's working folders
are left as they are.

Every loader goes through this module and fails closed:

* ``load(model_id)`` (STRAT-003, the backtester, the signal engine) refuses a folder
  without a manifest, a manifest that does not match its files, a manifest with an
  absolute path, a model_id that is not a plain folder name, and a store that overlaps
  the trainer's working root. Each refusal raises ``ModelStoreError`` and logs an ERROR.
* ``find_published(folder, coin=...)`` (the legacy neural runner) looks for a published
  manifest for that coin whose files match a coin folder's model files byte for byte,
  and returns it (the newest, if several runs produced the same files), or None. It
  reads the coin's models newest first and stops at the first match, so its cost does
  not grow with the store. Nothing is ever deleted from the store.

A model_id is derived from everything that identifies the run (``content_id``): the
files, the window, the seed, the candles and the code. Rerunning the same training
gives the same id and reuses the published folder; any difference gives a new one.

Manifests hold only paths relative to ``strategy_models_dir()`` (or the program
folder, for ``trainer_path``), so a model folder copied to another POWERTRADER_HOME
still loads.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
from typing import Optional

import pt_paths
from pattern_model import PatternModel, model_file_names

logger = logging.getLogger("model_store")

MANIFEST = "manifest.json"
MANIFEST_VERSION = 1
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# the trainer's ids: <COIN>-<train_end>-<12 hex>
TRAINER_ID_RE = re.compile(
    r"^(?P<coin>[A-Za-z0-9]+)-(?P<end>\d{8}T\d{4}Z)-[0-9a-f]{12}$"
)
REQUIRED_FIELDS = (
    "manifest_version",
    "model_id",
    "trainer_path",
    "trainer_git_commit",
    "upstream_commit",
    "symbol",
    "coin",
    "timeframes",
    "train_start",
    "train_end",
    "candle_file_sha256",
    "params",
    "seed",
    "created_at",
    "validation_metrics",
    "files",
)


class ModelStoreError(ValueError):
    """A model artifact that must not be used. Always logged as an ERROR."""


def _refuse(message: str) -> "ModelStoreError":
    logger.error(message)
    return ModelStoreError(message)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_model_id(model_id) -> str:
    """A plain folder name: letters, digits, '.', '_' and '-'; not '.' or '..'."""
    if model_id == "":
        raise _refuse("no model_id given: select a published model by its id")
    if not isinstance(model_id, str) or not MODEL_ID_RE.fullmatch(model_id):
        raise _refuse(f"invalid model_id {model_id!r}")
    if model_id in (".", "..") or set(model_id) == {"."}:
        raise _refuse(f"invalid model_id {model_id!r}")
    return model_id


def model_dir(model_id: str, create: bool = False) -> str:
    """``strategy_models_dir() / model_id``. Never resolves outside the store (so a
    model_id such as ``ETH`` can never point at a coin folder)."""
    validate_model_id(model_id)
    store = os.path.realpath(pt_paths.strategy_models_dir(create=create))
    path = os.path.realpath(os.path.join(store, model_id))
    if os.path.dirname(path) != store:
        raise _refuse(f"model_id {model_id!r} resolves outside the model store")
    return path


def configured_trainer_root() -> str:
    """The trainer's working root as the hub, the thinker and the trader resolve it
    (``main_neural_dir`` in the GUI settings, default ``models_dir()``), without
    creating anything."""
    path = os.environ.get("POWERTRADER_GUI_SETTINGS") or os.path.join(
        pt_paths.config_dir(create=False), pt_paths.GUI_SETTINGS_FILE
    )
    configured = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            configured = data.get("main_neural_dir")
    except (OSError, ValueError):
        configured = None
    return pt_paths.trainer_root(configured)


def check_no_overlap(trainer_root: Optional[str] = None) -> None:
    """Refuse when the trainer's working root is, contains or is inside the store
    (addendum 4.1): a model there could be deleted or overwritten by training."""
    root = trainer_root if trainer_root is not None else configured_trainer_root()
    store = pt_paths.strategy_models_dir(create=False)
    if pt_paths.paths_overlap(root, store):
        raise _refuse(
            f"the trainer's working root {root} overlaps the model store {store}; "
            "set main_neural_dir to a folder outside it"
        )


def _absolute_paths(value, where="manifest"):
    """Every string in the manifest that looks like an absolute path."""
    found = []
    if isinstance(value, dict):
        for k, v in value.items():
            found += _absolute_paths(v, f"{where}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            found += _absolute_paths(v, f"{where}[{i}]")
    elif isinstance(value, str):
        # absolute on any platform: a drive (C:\, C:/), a root (/, \), a UNC share or
        # a home folder (~); os.path.isabs alone differs between Windows and POSIX
        if (
            os.path.isabs(value)
            or re.match(r"^[A-Za-z]:[\\/]", value)
            or value.startswith(("/", "\\", "~"))
        ):
            found.append(where)
    return found


def read_manifest(folder: str) -> dict:
    path = os.path.join(folder, MANIFEST)
    if not os.path.isfile(path):
        raise _refuse(f"model {os.path.basename(folder)}: no {MANIFEST}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError) as exc:
        raise _refuse(f"model {os.path.basename(folder)}: unreadable manifest: {exc}")
    if not isinstance(manifest, dict):
        raise _refuse(f"model {os.path.basename(folder)}: manifest is not an object")
    return manifest


def verify_folder(folder: str, expected_id: Optional[str] = None) -> dict:
    """Check a published model folder against its manifest; return the manifest."""
    name = os.path.basename(os.path.normpath(folder))
    manifest = read_manifest(folder)
    missing = [k for k in REQUIRED_FIELDS if k not in manifest]
    if missing:
        raise _refuse(f"model {name}: manifest lacks {missing}")
    if manifest["manifest_version"] != MANIFEST_VERSION:
        raise _refuse(
            f"model {name}: manifest version {manifest['manifest_version']!r} "
            f"(expected {MANIFEST_VERSION})"
        )
    if manifest["model_id"] != (expected_id or name):
        raise _refuse(
            f"model {name}: manifest model_id {manifest['model_id']!r} does not match"
        )
    absolute = _absolute_paths(manifest)
    if absolute:
        raise _refuse(f"model {name}: absolute paths in the manifest at {absolute}")
    files = manifest["files"]
    if not isinstance(files, dict) or sorted(files) != model_file_names():
        raise _refuse(f"model {name}: the manifest does not list the 35 model files")
    try:
        present = sorted(
            n for n in os.listdir(folder) if n != MANIFEST and not n.startswith(".")
        )
        if present != model_file_names():
            extra = sorted(set(present) - set(model_file_names()))
            lost = sorted(set(model_file_names()) - set(present))
            raise _refuse(
                f"model {name}: files do not match (missing {lost}, extra {extra})"
            )
        for file_name, digest in files.items():
            if sha256_file(os.path.join(folder, file_name)) != digest:
                raise _refuse(f"model {name}: {file_name} does not match its manifest")
    except OSError as exc:
        raise _refuse(f"model {name}: unreadable model files: {exc}")
    return manifest


class LoadedModel:
    """A verified published model: its manifest and its parsed files."""

    def __init__(self, model_id: str, folder: str, manifest: dict, model: PatternModel):
        self.model_id = model_id
        self.folder = folder
        self.manifest = manifest
        self.model = model

    @property
    def train_end(self) -> str:
        return self.manifest["train_end"]


def load(model_id: str, trainer_root: Optional[str] = None) -> LoadedModel:
    """Load a published model by id. Fails closed (``ModelStoreError``, ERROR logged)."""
    folder = model_dir(model_id)
    check_no_overlap(trainer_root)
    if not os.path.isdir(folder):
        raise _refuse(f"model {model_id}: not found in the model store")
    manifest = verify_folder(folder, model_id)
    try:
        model = PatternModel.from_folder(folder)
    except (OSError, ValueError) as exc:
        raise _refuse(f"model {model_id}: unreadable model files: {exc}")
    return LoadedModel(model_id, folder, manifest, model)


def content_id(prefix: str, identity: dict) -> str:
    """A model_id derived from ``identity`` (JSON-serialisable: the files' hashes, the
    window, the seed, the candles, the code): the same run gives the same id, and any
    difference in what the manifest records about it gives another."""
    text = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return validate_model_id(f"{prefix}-{digest[:12]}")


_replace = os.replace


def _install(staging: str, final: str) -> None:
    """Rename the staging folder into place. On Windows a folder holding a file that a
    scanner or indexer has open cannot be renamed for a moment: retry briefly (unless
    the target has appeared, which the caller handles)."""
    for attempt in range(10):
        try:
            _replace(staging, final)
            return
        except PermissionError:
            if attempt == 9 or os.path.exists(final):
                raise
            time.sleep(0.2)


def publish(source_folder: str, manifest: dict, trainer_root: Optional[str]) -> str:
    """Copy the 35 model files from ``source_folder`` into the store with ``manifest``
    (whose ``files`` must hold their SHA-256). Returns the model folder. An identical
    model already published is reused; a different one under the same id is refused."""
    model_id = validate_model_id(manifest["model_id"])
    check_no_overlap(trainer_root)
    if pt_paths.paths_overlap(
        source_folder, pt_paths.strategy_models_dir(create=False)
    ):
        raise _refuse(f"model {model_id}: the source folder overlaps the model store")
    files = manifest["files"]
    for name in model_file_names():
        if sha256_file(os.path.join(source_folder, name)) != files.get(name):
            raise _refuse(f"model {model_id}: {name} changed before publishing")
    absolute = _absolute_paths(manifest)
    if absolute:
        raise _refuse(f"model {model_id}: absolute paths in the manifest at {absolute}")
    store = pt_paths.strategy_models_dir(create=True)
    final = model_dir(model_id, create=True)
    if os.path.isdir(final):
        existing = verify_folder(final, model_id)
        if existing["files"] != files:
            raise _refuse(f"model {model_id}: already published with other files")
        return final
    # a short staging name: no path in it is longer than in the final folder (Windows
    # refuses paths of 260 characters or more unless long paths are enabled)
    staging = tempfile.mkdtemp(prefix=".stage-", dir=store)
    try:
        try:
            for name in model_file_names():
                shutil.copyfile(
                    os.path.join(source_folder, name), os.path.join(staging, name)
                )
            pt_paths.write_private_text(
                os.path.join(staging, MANIFEST),
                json.dumps(manifest, indent=2, sort_keys=True),
            )
        except OSError as exc:
            raise _refuse(f"model {model_id}: could not copy it into the store: {exc}")
        verify_folder(staging, model_id)
        try:
            _install(staging, final)
        except OSError as exc:
            # another run published the same id meanwhile: reuse it if identical
            if os.path.isdir(final):
                existing = verify_folder(final, model_id)
                if existing["files"] == files:
                    shutil.rmtree(staging, ignore_errors=True)
                    return final
            raise _refuse(f"model {model_id}: could not publish: {exc}")
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final


def _peek_manifest(folder: str) -> Optional[dict]:
    """A manifest read without complaint (for scanning the store)."""
    try:
        with open(os.path.join(folder, MANIFEST), "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def folder_file_hashes(folder: str) -> Optional[dict]:
    """SHA-256 of the 35 model files in a coin folder, or None if any is missing."""
    out = {}
    for name in model_file_names():
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            return None
        out[name] = sha256_file(path)
    return out


def find_published(
    folder: str, trainer_root: Optional[str] = None, coin: Optional[str] = None
) -> Optional[dict]:
    """The manifest of the published model whose files match ``folder``'s model files
    byte for byte (the legacy neural runner's check), or None; with ``coin``, only a
    model trained for that coin. Of several matches (the same files from runs that
    differ otherwise), the newest. Logs an ERROR when there is none."""
    check_no_overlap(trainer_root)
    try:
        hashes = folder_file_hashes(folder)
    except OSError as exc:
        logger.error("unreadable model files in %s: %s", folder, exc)
        return None
    if hashes is None:
        logger.error("no complete set of model files in %s", folder)
        return None
    store = pt_paths.strategy_models_dir(create=False)
    names = os.listdir(store) if os.path.isdir(store) else []
    # the trainer's models of this coin, newest train_end first, a group per train_end;
    # then any folder not named like a trainer model
    by_end, other = {}, []
    for name in names:
        if name.startswith("."):
            continue
        m = TRAINER_ID_RE.match(name)
        if m is None:
            other.append(name)
        elif coin is None or m["coin"] == coin:
            by_end.setdefault(m["end"], []).append(name)
    groups = [sorted(by_end[end]) for end in sorted(by_end, reverse=True)]
    for group in groups + [sorted(other)]:
        found = [
            m
            for m in (_matching(store, n, hashes, coin, folder) for n in group)
            if m is not None
        ]
        if found:
            return max(found, key=lambda m: str(m.get("created_at")))
    logger.error("no published manifest matches the model files in %s", folder)
    return None


def _matching(store, name, hashes, coin, folder) -> Optional[dict]:
    """The verified manifest of ``store/name`` if its files are ``hashes`` (and it was
    trained for ``coin``), else None."""
    candidate = os.path.join(store, name)
    if not os.path.isdir(candidate):
        return None
    manifest = _peek_manifest(candidate)
    if manifest is None or manifest.get("files") != hashes:
        return None
    if coin is not None and manifest.get("coin") != coin:
        logger.error(
            "model %s matches the files in %s but was trained for %s, not %s",
            name,
            folder,
            manifest.get("coin"),
            coin,
        )
        return None
    try:
        return verify_folder(candidate)
    except ModelStoreError:
        return None
