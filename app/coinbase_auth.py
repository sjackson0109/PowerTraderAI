"""
Coinbase Advanced Trade / CDP API key authentication.

Current scheme (docs.cdp.coinbase.com, "API key authentication"): a CDP API key is
a *key name* (``organizations/{org_id}/apiKeys/{key_id}``) plus an ECDSA (P-256)
*private key* in PEM form. Every request carries a fresh ES256 JWT, valid for two
minutes, in ``Authorization: Bearer <jwt>``:

    header   {"alg": "ES256", "typ": "JWT", "kid": <key name>, "nonce": <random hex>}
    payload  {"sub": <key name>, "iss": "cdp", "nbf": <now>, "exp": <now + 120>,
              "uri": "<METHOD> <host><path>"}

The retired Coinbase Pro scheme (key + secret + passphrase, HMAC) and the old
HMAC key/secret scheme are not accepted by the Advanced Trade API, and Ed25519
keys are not supported by Coinbase's App SDKs, so this module accepts only an
EC P-256 key.

Nothing here logs or returns key material; error messages describe the problem
without echoing what was pasted.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import textwrap
import time
from typing import Optional

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

JWT_LIFETIME_SECONDS = 120

_KEY_NAME_RE = re.compile(r"^organizations/[^/\s]+/apiKeys/[^/\s]+$")
_PEM_RE = re.compile(
    r"-----BEGIN (?P<label>[A-Z0-9 ]*PRIVATE KEY)-----(?P<body>.*?)-----END (?P=label)-----",
    re.DOTALL,
)


class CoinbaseCredentialError(ValueError):
    """The pasted key name / private key cannot be used. The message is safe to show."""


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def validate_key_name(key_name: str) -> str:
    name = (key_name or "").strip()
    if not name:
        raise CoinbaseCredentialError("The key name is empty.")
    if not _KEY_NAME_RE.match(name):
        raise CoinbaseCredentialError(
            "The key name must look like organizations/<org-id>/apiKeys/<key-id>. "
            "Short API keys with a separate secret (and Coinbase Pro keys with a "
            "passphrase) are the retired scheme and do not work with the current API."
        )
    return name


def normalise_private_key(raw: str) -> str:
    """Return a clean PEM from whatever was pasted.

    Accepts real newlines, literal ``\\n`` escapes (as in the JSON file Coinbase
    lets you download), CRLF, surrounding quotes/whitespace, and a body that was
    flattened onto one line. The BEGIN/END lines are required.
    """
    text = (raw or "").strip().strip("\"'").strip()
    if not text:
        raise CoinbaseCredentialError("The private key is empty.")
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n")
    match = _PEM_RE.search(text)
    if not match:
        raise CoinbaseCredentialError(
            "The private key must include the '-----BEGIN EC PRIVATE KEY-----' and "
            "'-----END EC PRIVATE KEY-----' lines."
        )
    label = match.group("label")
    body = re.sub(r"\s+", "", match.group("body"))
    if not body:
        raise CoinbaseCredentialError(
            "The private key has no content between BEGIN and END."
        )
    wrapped = "\n".join(textwrap.wrap(body, 64))
    return f"-----BEGIN {label}-----\n{wrapped}\n-----END {label}-----\n"


def load_private_key(raw_pem: str) -> ec.EllipticCurvePrivateKey:
    """Parse and check the key. Raises CoinbaseCredentialError; never echoes the key."""
    pem = normalise_private_key(raw_pem)
    try:
        key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    except TypeError:
        raise CoinbaseCredentialError(
            "The private key is encrypted with a passphrase; use the unencrypted key "
            "Coinbase gave you."
        ) from None
    except (ValueError, UnsupportedAlgorithm):
        raise CoinbaseCredentialError(
            "The private key could not be parsed. Paste it exactly as Coinbase "
            "showed it, including the BEGIN/END lines."
        ) from None
    if isinstance(key, ed25519.Ed25519PrivateKey):
        raise CoinbaseCredentialError(
            "This is an Ed25519 key. The Advanced Trade API needs an ECDSA key: "
            "create a new API key and choose ECDSA as the signature algorithm."
        )
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise CoinbaseCredentialError(
            "The private key is not an EC key. Create the API key with the ECDSA "
            "signature algorithm."
        )
    if not isinstance(key.curve, ec.SECP256R1):
        raise CoinbaseCredentialError(
            f"The private key uses curve {key.curve.name}; Coinbase needs P-256 (ES256)."
        )
    return key


def build_uri_claim(method: str, host: str, path: str) -> str:
    """``"GET api.coinbase.com/api/v3/brokerage/accounts"`` - no scheme.

    Paths with a query string are refused: the CDP docs show the claim as
    ``METHOD host path`` and do not say how a query is treated, so signing one
    would be a guess. Every call this app makes has a plain path.
    """
    if "?" in path:
        raise ValueError("uri claim paths must not contain a query string")
    return f"{method.upper()} {host}{path}"


def build_jwt(
    key_name: str,
    private_key: ec.EllipticCurvePrivateKey,
    method: str,
    host: str,
    path: str,
    now: Optional[float] = None,
    nonce: Optional[str] = None,
) -> str:
    """A fresh per-request ES256 JWT for ``method host path``."""
    issued = int(time.time() if now is None else now)
    header = {
        "alg": "ES256",
        "typ": "JWT",
        "kid": key_name,
        "nonce": nonce if nonce is not None else secrets.token_hex(16),
    }
    payload = {
        "sub": key_name,
        "iss": "cdp",
        "nbf": issued,
        "exp": issued + JWT_LIFETIME_SECONDS,
        "uri": build_uri_claim(method, host, path),
    }
    signing_input = ".".join(
        _b64url(json.dumps(part, separators=(",", ":")).encode("utf-8"))
        for part in (header, payload)
    )
    der = private_key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    # JWS ES256 signatures are the fixed-width concatenation r || s, not DER.
    signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{signing_input}.{_b64url(signature)}"
