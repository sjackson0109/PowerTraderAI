"""
Coinbase Advanced Trade / CDP API key authentication.

Current scheme (docs.cdp.coinbase.com, "API key authentication"): a CDP API key is
a *key name* (``organizations/{org_id}/apiKeys/{key_id}``) plus a *private key* of
one of two types, chosen when the key is created:

* **Ed25519** (the portal's default, "recommended"): one line of standard base64
  that decodes to 64 bytes, the 32-byte seed followed by the 32-byte public key.
  Requests are signed with EdDSA.
* **ECDSA** (shown as "legacy", still supported): a P-256 key in PEM form, with
  ``-----BEGIN EC PRIVATE KEY-----`` / ``-----END EC PRIVATE KEY-----`` lines.
  Requests are signed with ES256.

The Advanced Trade API accepts both ("Direct API calls work with both", CDP
authentication overview; Coinbase's coinbase-advanced-py signs either since 1.8.3).
Every request carries a fresh JWT, valid for two minutes, in
``Authorization: Bearer <jwt>``; only ``alg`` and the signature differ:

    header   {"alg": "EdDSA" | "ES256", "typ": "JWT", "kid": <key name>,
              "nonce": <random hex>}
    payload  {"sub": <key name>, "iss": "cdp", "nbf": <now>, "exp": <now + 120>,
              "uri": "<METHOD> <host><path>"}

The retired Coinbase Pro scheme (key + secret + passphrase, HMAC) and the old
HMAC key/secret scheme are not accepted by the Advanced Trade API.

Nothing here logs or returns key material; error messages describe the problem
without echoing what was pasted.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import secrets
import textwrap
import time
from typing import Optional, Union

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

JWT_LIFETIME_SECONDS = 120

# A Coinbase Ed25519 secret decodes to seed || public key (64 bytes). Only that
# form is accepted: its public half lets a wrong paste (a bare 32-byte seed such
# as a Robinhood key, or a retired Coinbase Exchange secret, also 64 bytes) be
# caught here instead of failing at Coinbase with HTTP 401.
ED25519_SECRET_BYTES = 64
ED25519_SEED_BYTES = 32

CoinbasePrivateKey = Union[ec.EllipticCurvePrivateKey, ed25519.Ed25519PrivateKey]

_KEY_NAME_RE = re.compile(r"^organizations/[^/\s]+/apiKeys/[^/\s]+$")
# Some Ed25519 keys are shown with just their key ID, a UUID; Coinbase's SDKs use it
# as kid/sub as given. Retired keys never match it (no dashes).
_KEY_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_PEM_RE = re.compile(
    r"-----BEGIN (?P<label>[A-Z0-9 ]*PRIVATE KEY)-----(?P<body>.*?)-----END (?P=label)-----",
    re.DOTALL,
)
_NOT_A_KEY = (
    "The private key is not one Coinbase issues. Paste it exactly as Coinbase "
    "showed it: for an Ed25519 key, the single line of base64; for an ECDSA key, "
    "the whole block including the '-----BEGIN EC PRIVATE KEY-----' and "
    "'-----END EC PRIVATE KEY-----' lines."
)


class CoinbaseCredentialError(ValueError):
    """The pasted key name / private key cannot be used. The message is safe to show."""


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def validate_key_name(key_name: str) -> str:
    name = (key_name or "").strip()
    if not name:
        raise CoinbaseCredentialError("The key name is empty.")
    if not (_KEY_NAME_RE.match(name) or _KEY_ID_RE.match(name)):
        raise CoinbaseCredentialError(
            "The key name must look like organizations/<org-id>/apiKeys/<key-id> "
            "(or, for some Ed25519 keys, the key ID: a UUID). Old short API keys with "
            "a separate secret, and Coinbase Pro keys with a passphrase, are retired "
            "and do not work with the current API."
        )
    return name


def _clean(raw: str) -> str:
    """Strip surrounding whitespace/quotes and undo JSON-style escapes and CRLF."""
    text = (raw or "").strip().strip("\"'").strip()
    if not text:
        raise CoinbaseCredentialError("The private key is empty.")
    return text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n")


def _is_pem(text: str) -> bool:
    return "-----BEGIN" in text or "-----END" in text


def _is_der_ec_key(raw: bytes) -> bool:
    """True when ``raw`` is an EC private key in DER (a PEM body without its lines)."""
    try:
        key = serialization.load_der_private_key(raw, password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm):
        return False
    return isinstance(key, ec.EllipticCurvePrivateKey)


def _ed25519_secret_bytes(text: str) -> bytes:
    """The decoded 64 bytes of a base64 Ed25519 secret, or raise."""
    compact = re.sub(r"\s+", "", text)
    raw = None
    for altchars in (None, b"-_"):  # standard base64 as issued; URL-safe tolerated
        try:
            padded = compact + "=" * (-len(compact) % 4)
            raw = base64.b64decode(padded, altchars=altchars, validate=True)
            break
        except (binascii.Error, ValueError):
            continue
    if raw is not None and len(raw) == ED25519_SECRET_BYTES:
        return raw
    if raw is not None and _is_der_ec_key(raw):
        raise CoinbaseCredentialError(
            "This looks like an ECDSA key without its BEGIN/END lines (such as "
            "'-----BEGIN EC PRIVATE KEY-----'). Paste the whole block exactly as "
            "Coinbase showed it, including those lines."
        )
    raise CoinbaseCredentialError(_NOT_A_KEY)


def normalise_private_key(raw: str) -> str:
    """Return the key in a clean, canonical form, ready to store.

    An ECDSA key comes back as a wrapped PEM. Accepts real newlines, literal
    ``\\n`` escapes (as in the JSON file Coinbase lets you download), CRLF,
    surrounding quotes/whitespace, and a body flattened onto one line. The
    BEGIN/END lines are required.

    An Ed25519 key comes back as one line of standard base64 (stray whitespace,
    surrounding quotes, missing padding or URL-safe characters are tidied).
    """
    text = _clean(raw)
    if not _is_pem(text):
        return base64.b64encode(_ed25519_secret_bytes(text)).decode("ascii")
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


def _load_ed25519(text: str) -> ed25519.Ed25519PrivateKey:
    raw = _ed25519_secret_bytes(text)
    key = ed25519.Ed25519PrivateKey.from_private_bytes(raw[:ED25519_SEED_BYTES])
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    if public != raw[ED25519_SEED_BYTES:]:
        raise CoinbaseCredentialError(
            "The private key is not a valid Coinbase Ed25519 key (its two halves do "
            "not match). Paste it exactly as Coinbase showed it."
        )
    return key


def load_private_key(raw_key: str) -> CoinbasePrivateKey:
    """Parse and check the key: an Ed25519 key (base64) or an ECDSA P-256 key (PEM).

    Raises CoinbaseCredentialError; never echoes the key."""
    if not _is_pem(_clean(raw_key)):
        return _load_ed25519(_clean(raw_key))
    pem = normalise_private_key(raw_key)
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
        return key  # an Ed25519 key in PKCS#8 PEM form signs the same way
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise CoinbaseCredentialError(
            "The private key is neither an Ed25519 nor an ECDSA key. Create the API "
            "key with the Ed25519 (recommended) or ECDSA signature algorithm."
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


def jwt_algorithm(private_key: CoinbasePrivateKey) -> str:
    """``"EdDSA"`` for an Ed25519 key, ``"ES256"`` for an ECDSA P-256 key."""
    if isinstance(private_key, ed25519.Ed25519PrivateKey):
        return "EdDSA"
    if isinstance(private_key, ec.EllipticCurvePrivateKey):
        return "ES256"
    raise TypeError("unsupported Coinbase private key type")


def build_jwt(
    key_name: str,
    private_key: CoinbasePrivateKey,
    method: str,
    host: str,
    path: str,
    now: Optional[float] = None,
    nonce: Optional[str] = None,
) -> str:
    """A fresh per-request JWT for ``method host path`` (EdDSA or ES256)."""
    issued = int(time.time() if now is None else now)
    alg = jwt_algorithm(private_key)
    header = {
        "alg": alg,
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
    if alg == "EdDSA":
        # JWS EdDSA signatures are the raw 64-byte Ed25519 signature.
        signature = private_key.sign(signing_input.encode("ascii"))
    else:
        der = private_key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        # JWS ES256 signatures are the fixed-width concatenation r || s, not DER.
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{signing_input}.{_b64url(signature)}"
