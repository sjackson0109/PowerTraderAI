"""
The registered artifact and the code hash (FDS-SIG-004 sections 5.9 and 6.6).

**One implementation.** The harness, the backtester and the trader call the same
functions: this package, and the feature blocks it imports from ``model_lab.features``.
``code_hash`` is the SHA-256 (LF line endings) of those files.

**The registered artifact.** For a forward window, one file holds the fitted models, the
calibrator, the payoff tables, σ_ref, the tercile cut points and the code hash; its own
SHA-256 is part of the registration. The live hook loads only that file (``load``): a
missing file, a changed file or a code hash that differs from today's makes the predictive
part unavailable, so a window cannot quietly run on an updated model.

No artifact is registered yet: registration (phase D) needs the owner's go-ahead.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
from typing import Any, Dict, Optional, Tuple

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = ("model_lab/features.py",)


def code_files():
    here = sorted(
        os.path.relpath(p, APP).replace("\\", "/")
        for p in glob.glob(os.path.join(APP, "signal_fusion", "*.py"))
    )
    return here + list(SHARED)


def code_hash() -> str:
    h = hashlib.sha256()
    for name in code_files():
        with open(os.path.join(APP, name), "rb") as f:
            h.update(name.encode("utf-8"))
            h.update(f.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def _canonical(body: Dict[str, Any]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def seal(body: Dict[str, Any]) -> Dict[str, Any]:
    """The artifact with its code hash and its own SHA-256."""
    body = {
        **{k: v for k, v in body.items() if k != "sha256"},
        "code_hash": code_hash(),
    }
    return {**body, "sha256": hashlib.sha256(_canonical(body)).hexdigest()}


def load(
    path: Optional[str], registered_sha256: Optional[str]
) -> Tuple[Optional[Dict[str, Any]], str]:
    """(the artifact, "") when it is the registered one and today's code is its code;
    otherwise (None, the reason)."""
    if not path or not registered_sha256:
        return None, "no registered model"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        return None, f"the registered model cannot be read ({type(exc).__name__})"
    body = {k: v for k, v in data.items() if k != "sha256"}
    if hashlib.sha256(_canonical(body)).hexdigest() != data.get("sha256"):
        return None, "the registered model's file has changed"
    if data.get("sha256") != registered_sha256:
        return None, "this is not the registered model"
    if data.get("code_hash") != code_hash():
        return None, "the assessment's code has changed since registration"
    return data, ""
