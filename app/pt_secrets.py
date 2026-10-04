"""
API credentials for PowerTraderAI (FDS-108a).

This is the ONLY module that reads or writes credentials. Secrets live in the
operating system's credential store through the ``keyring`` library:

* Windows: Credential Manager
* macOS: Keychain
* Linux: Secret Service (GNOME Keyring, KWallet, ...)

Service name ``SJackson.PowerTraderAI``; one entry per field, named
``<exchange>:<field>`` (``coinbase:key_name``, ``coinbase:private_key``,
``binance:api_key``, ...).

Precedence (defined here and nowhere else)
------------------------------------------
1. Environment variables (CI, headless servers, Docker).
2. The OS keyring.

A source is used for an exchange only when it holds every required field for
that exchange; values are never mixed between sources. When both hold a full
set, the environment wins and a warning names the source used (never a value).

Environment variables
---------------------
================ ===================== ====================================== =====================
Exchange         Keyring entry         Environment variable                   Connector argument
================ ===================== ====================================== =====================
coinbase         ``coinbase:key_name``    ``POWERTRADER_COINBASE_API_KEY``       ``api_key``
coinbase         ``coinbase:private_key`` ``POWERTRADER_COINBASE_API_SECRET``    ``api_secret``
robinhood        ``robinhood:api_key``    ``POWERTRADER_ROBINHOOD_API_KEY``      ``api_key``
robinhood        ``robinhood:private_key`` ``POWERTRADER_ROBINHOOD_PRIVATE_KEY``  ``api_secret``
                                          (or ``POWERTRADER_ROBINHOOD_API_SECRET``)
aave, yearn_finance, ``<x>:private_key``  ``POWERTRADER_<X>_PRIVATE_KEY``        ``private_key``
lido_finance
smtp (alerts)    ``smtp:password``        ``POWERTRADER_SMTP_PASSWORD``          ``password``
any other        ``<x>:api_key``          ``POWERTRADER_<X>_API_KEY``            ``api_key``
any other        ``<x>:api_secret``       ``POWERTRADER_<X>_API_SECRET``         ``api_secret``
any other        ``<x>:passphrase``       ``POWERTRADER_<X>_PASSPHRASE``         ``passphrase``
                                          (optional; KuCoin, Bitget, dYdX)
================ ===================== ====================================== =====================

``<X>`` is the exchange id in upper case (``KRAKEN``, ``CRYPTO_COM``, ...).

No plaintext fallback
---------------------
If no usable keyring backend exists (for example a headless Linux box without
Secret Service), nothing is stored: ``set_secret`` raises
``KeyringUnavailable`` with a message naming the environment variables to use
instead, and the app keeps running in paper mode. Backends that write to a
plain file (``keyrings.alt``) are refused. The same happens when the
``keyring`` package itself is not installed; the message then names the
package and how to install it (the cause is logged once).

Values never appear in logs, exceptions or ``repr()``: reads return
``Secret`` / ``Credentials`` objects whose ``repr`` is redacted.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

import pt_paths

logger = logging.getLogger("pt_secrets")

SERVICE_NAME = "SJackson.PowerTraderAI"

# Windows Credential Manager limit: CRED_MAX_CREDENTIAL_BLOB_SIZE = 5 * 512 bytes,
# and keyring stores the value as UTF-16 (2 bytes per code unit), so about 1,280
# characters. The largest secret PowerTrader stores, a Coinbase EC private key
# PEM, is about 230 characters. Enforced on every platform so behaviour does not
# depend on the OS.
MAX_SECRET_BYTES = 2560

SOURCE_ENV = "environment"
SOURCE_KEYRING = "keyring"

REDACTED = "***"


class SecretsError(RuntimeError):
    """Base class. Messages name exchanges and fields, never values."""


class KeyringUnavailable(SecretsError):
    """No usable OS credential store; nothing was stored."""


class SecretTooLarge(SecretsError, ValueError):
    """The value is larger than the OS credential store accepts."""


class UnknownSecretField(SecretsError, ValueError):
    """The field is not a credential field of that exchange."""


class Secret:
    """A credential value that never shows itself by accident.

    ``repr``, ``str`` and ``format`` print ``***``; it cannot be pickled or
    JSON-encoded. Call ``reveal()`` at the one place the real value is needed
    (building the connector).
    """

    __slots__ = ("_value",)

    def __init__(self, value: str):
        object.__setattr__(self, "_value", str(value))

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"Secret({REDACTED!r})"

    def __str__(self) -> str:
        return REDACTED

    def __format__(self, spec: str) -> str:
        return REDACTED

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Secret):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Secret", self._value))

    def __setattr__(self, name, value):
        raise AttributeError("Secret is immutable")

    def __reduce__(self):
        raise TypeError("Secret values cannot be pickled")


class Credentials(dict):
    """Connector keyword arguments (``api_key=...``) with a redacted ``repr``.

    It is a real ``dict`` so ``Exchange(**creds)`` works; ``source`` says where
    the values came from (``"environment"`` or ``"keyring"``).
    """

    def __init__(self, exchange: str, source: str, values: Dict[str, str]):
        super().__init__(values)
        self.exchange = exchange
        self.source = source

    def __repr__(self) -> str:
        names = ", ".join(f"{k}={REDACTED}" for k in self)
        return f"Credentials({self.exchange}: {names} from {self.source})"

    __str__ = __repr__


@dataclass(frozen=True)
class SecretField:
    name: str  # keyring entry is "<exchange>:<name>"
    kwarg: str  # connector constructor argument
    env: Tuple[str, ...]  # environment variable names, first set one wins
    required: bool = True


def _env(exchange: str, suffix: str) -> str:
    return f"POWERTRADER_{exchange.upper()}_{suffix}"


def _fields(exchange: str) -> Tuple[SecretField, ...]:
    x = exchange
    if x == "coinbase":
        return (
            SecretField("key_name", "api_key", (_env(x, "API_KEY"),)),
            SecretField("private_key", "api_secret", (_env(x, "API_SECRET"),)),
        )
    if x == "robinhood":
        return (
            SecretField("api_key", "api_key", (_env(x, "API_KEY"),)),
            SecretField(
                "private_key",
                "api_secret",
                (_env(x, "PRIVATE_KEY"), _env(x, "API_SECRET")),
            ),
        )
    if x in ("aave", "yearn_finance", "lido_finance"):
        return (SecretField("private_key", "private_key", (_env(x, "PRIVATE_KEY"),)),)
    if x == "smtp":  # alert e-mails (pt_live_monitor)
        return (SecretField("password", "password", (_env(x, "PASSWORD"),)),)
    return (
        SecretField("api_key", "api_key", (_env(x, "API_KEY"),)),
        SecretField("api_secret", "api_secret", (_env(x, "API_SECRET"),)),
        SecretField(
            "passphrase", "passphrase", (_env(x, "PASSPHRASE"),), required=False
        ),
    )


def normalise_exchange(exchange: str) -> str:
    name = str(exchange or "").strip().lower()
    if not name or ":" in name:
        raise UnknownSecretField(f"invalid exchange id {exchange!r}")
    return name


def secret_fields(exchange: str) -> Tuple[SecretField, ...]:
    """The credential fields of ``exchange``, in display order."""
    return _fields(normalise_exchange(exchange))


def field_for_kwarg(exchange: str, kwarg: str) -> Optional[str]:
    """Keyring field name for a connector argument (``api_secret`` -> ``private_key``)."""
    for f in secret_fields(exchange):
        if f.kwarg == kwarg:
            return f.name
    return None


def env_var_names(exchange: str) -> Tuple[str, ...]:
    """Every environment variable that can supply ``exchange`` credentials."""
    return tuple(name for f in secret_fields(exchange) for name in f.env)


def is_secret_key(name: str) -> bool:
    """True for config keys that hold a credential and must never be written to
    a config file (``api_key``, ``api_secret``, ``private_key``,
    ``webhook_secret``, ``smtp_password``, ...)."""
    key = str(name).strip().lower().replace("-", "_")
    return key in SECRET_CONFIG_KEYS or key.endswith(SECRET_KEY_SUFFIXES)


SECRET_KEY_SUFFIXES = (
    "_secret",
    "_password",
    "_passphrase",
    "_token",
    "_private_key",
    "_api_key",
)


def strip_secret_fields(data, where: str = "config", warn: bool = True):
    """A copy of ``data`` (nested dicts/lists) without credential keys.

    A credential key holding a value is reported with a warning that names the
    file and the key path, never the value (``warn=False`` for the migration,
    which has just moved those values to the keyring). Use it on every config
    read so a secret that ended up in a file is ignored and never written back.
    """

    def walk(node, path):
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                here = f"{path}.{key}" if path else str(key)
                if isinstance(key, str) and is_secret_key(key):
                    if warn and value not in (None, "", [], {}):
                        logger.warning(
                            "%s holds a credential field (%s); it is ignored and will not be "
                            "written back. Credentials belong in the OS keyring "
                            "(setup window, or pt_migrate.py).",
                            where,
                            here,
                        )
                    continue
                out[key] = walk(value, here)
            return out
        if isinstance(node, list):
            return [walk(v, f"{path}[{i}]") for i, v in enumerate(node)]
        return node

    return walk(data, "")


# Keys that, wherever they appear in a config file, are credentials.
SECRET_CONFIG_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "secret_key",
        "private_key",
        "passphrase",
        "password",
        "key_name",
        "access_token",
        "refresh_token",
    }
)


def _field(exchange: str, field: str) -> SecretField:
    for f in secret_fields(exchange):
        if f.name == field:
            return f
    raise UnknownSecretField(
        f"{field!r} is not a credential field for {exchange!r} "
        f"(expected one of: {', '.join(f.name for f in secret_fields(exchange))})"
    )


def entry_name(exchange: str, field: str) -> str:
    exchange = normalise_exchange(exchange)
    return f"{exchange}:{_field(exchange, field).name}"


# --- keyring backend ----------------------------------------------------------


def _refused_backend(backend) -> bool:
    """Backends that would store nothing, or store in a plain file."""
    cls = type(backend)
    module = cls.__module__ or ""
    if module.startswith("keyrings.alt"):
        return True  # file-based backends: plaintext or a file next to the user's data
    if module in ("keyring.backends.fail", "keyring.backends.null"):
        return True
    return "plaintext" in cls.__name__.lower()


# True once the missing keyring package has been logged: the cause is logged once
# per process, not on every lookup.
_missing_package_logged = False


def _keyring_package():
    """``(keyring, ChainerBackend)``, or None when the keyring package is not
    installed (or cannot be loaded). The cause is logged once."""
    global _missing_package_logged
    try:
        import keyring
        from keyring.backends.chainer import ChainerBackend
    except ImportError as exc:
        if not _missing_package_logged:
            _missing_package_logged = True
            logger.warning(
                "The Python package 'keyring' is not installed (%s), so credentials cannot be "
                "read from or saved to the OS credential store. %s",
                exc,
                pt_paths.install_hint("keyring"),
            )
        return None
    return keyring, ChainerBackend


def keyring_package_missing() -> bool:
    """True when the keyring package itself is missing, as opposed to installed
    without a usable OS backend."""
    return _keyring_package() is None


def _backend():
    """The usable keyring backend, or None. A chained backend is narrowed to its
    first acceptable member, so a write can never fall through to a refused one."""
    package = _keyring_package()
    if package is None:
        return None
    keyring, ChainerBackend = package
    try:
        current = keyring.get_keyring()
    except Exception:
        return None
    members = (
        list(current.backends) if isinstance(current, ChainerBackend) else [current]
    )
    for backend in members:
        if not _refused_backend(backend):
            return backend
    return None


def keyring_available() -> bool:
    return _backend() is not None


def backend_name() -> str:
    backend = _backend()
    return type(backend).__name__ if backend is not None else "none"


def unavailable_message(exchange: Optional[str] = None) -> str:
    """Why credentials were not saved and what to do instead. Names the keyring
    package when that is what is missing, else the OS credential store."""
    names = (
        env_var_names(exchange)
        if exchange
        else (
            "POWERTRADER_<EXCHANGE>_API_KEY",
            "POWERTRADER_<EXCHANGE>_API_SECRET",
        )
    )
    if keyring_package_missing():
        return (
            "The Python package 'keyring' is not installed, so credentials were NOT saved: "
            "PowerTrader needs it to use the operating system's credential store and never "
            "stores API keys in a plain file. "
            + pt_paths.install_hint("keyring")
            + " Or set the credentials as environment variables ("
            + ", ".join(names)
            + "). Until then PowerTrader runs in paper mode."
        )
    return (
        "No secure credential store (OS keyring) is available on this system, so "
        "credentials were NOT saved. PowerTrader never stores API keys in a plain "
        "file. Set them as environment variables instead ("
        + ", ".join(names)
        + "); until then PowerTrader runs in paper mode."
    )


def _keyring_get(exchange: str, field: str) -> Optional[str]:
    backend = _backend()
    if backend is None:
        return None
    try:
        value = backend.get_password(SERVICE_NAME, f"{exchange}:{field}")
    except Exception as exc:
        logger.warning(
            "Could not read %s:%s from the OS keyring (%s)",
            exchange,
            field,
            type(exc).__name__,
        )
        return None
    return value or None


def _env_get(f: SecretField) -> Optional[str]:
    for name in f.env:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


# --- public API -----------------------------------------------------------------


def get_secret(exchange: str, field: str) -> Optional[Secret]:
    """One credential field: its environment variable first, then the keyring."""
    exchange = normalise_exchange(exchange)
    f = _field(exchange, field)
    value = _env_get(f)
    if value is None:
        value = _keyring_get(exchange, f.name)
    return Secret(value) if value else None


def check_size(exchange: str, field: str, value: str) -> None:
    size = len(str(value).encode("utf-16-le"))
    if size > MAX_SECRET_BYTES:
        raise SecretTooLarge(
            f"{exchange}:{field} is {size} bytes as stored; the OS credential store "
            f"accepts at most {MAX_SECRET_BYTES} bytes (about {MAX_SECRET_BYTES // 2} "
            "characters). Check that only the key itself was pasted."
        )


def set_secret(exchange: str, field: str, value) -> None:
    """Store one field in the OS keyring. An empty value deletes the entry.

    Raises ``KeyringUnavailable`` (nothing stored, no file written) when there
    is no usable keyring, ``SecretTooLarge`` for an oversized value.
    """
    exchange = normalise_exchange(exchange)
    f = _field(exchange, field)
    if isinstance(value, Secret):
        value = value.reveal()
    value = "" if value is None else str(value)
    if not value.strip():
        delete_secret(exchange, f.name)
        return
    check_size(exchange, f.name, value)
    backend = _backend()
    if backend is None:
        raise KeyringUnavailable(unavailable_message(exchange))
    try:
        if backend.get_password(SERVICE_NAME, f"{exchange}:{f.name}") == value:
            return  # unchanged
        backend.set_password(SERVICE_NAME, f"{exchange}:{f.name}", value)
    except Exception as exc:
        # `from None`: a backend exception must not carry the value into a traceback
        raise SecretsError(
            f"Could not save {exchange}:{f.name} to the OS keyring ({type(exc).__name__})."
        ) from None
    logger.info(
        "Saved %s:%s to the OS keyring (%s)", exchange, f.name, type(backend).__name__
    )


def delete_secret(exchange: str, field: str) -> bool:
    """Remove one field from the keyring. True when an entry was removed."""
    exchange = normalise_exchange(exchange)
    f = _field(exchange, field)
    backend = _backend()
    if backend is None:
        return False
    try:
        if backend.get_password(SERVICE_NAME, f"{exchange}:{f.name}") is None:
            return False
        backend.delete_password(SERVICE_NAME, f"{exchange}:{f.name}")
    except Exception as exc:
        logger.warning(
            "Could not delete %s:%s from the OS keyring (%s)",
            exchange,
            f.name,
            type(exc).__name__,
        )
        return False
    return True


def delete_credentials(exchange: str) -> int:
    """Remove every stored field of ``exchange``; returns how many were removed."""
    return sum(delete_secret(exchange, f.name) for f in secret_fields(exchange))


def set_credentials(exchange: str, values: Dict[str, object]) -> None:
    """Store several fields at once (keys are field names). Sizes and the
    backend are checked before anything is written."""
    exchange = normalise_exchange(exchange)
    pending = {}
    for field, value in values.items():
        f = _field(exchange, field)
        text = (
            value.reveal()
            if isinstance(value, Secret)
            else ("" if value is None else str(value))
        )
        if text.strip():
            check_size(exchange, f.name, text)
        pending[f.name] = text
    if any(v.strip() for v in pending.values()) and _backend() is None:
        raise KeyringUnavailable(unavailable_message(exchange))
    for field, text in pending.items():
        set_secret(exchange, field, text)


def _read_source(exchange: str, source: str) -> Dict[str, str]:
    values = {}
    for f in secret_fields(exchange):
        value = _env_get(f) if source == SOURCE_ENV else _keyring_get(exchange, f.name)
        if value:
            values[f.name] = value
    return values


# Exchanges already warned about (credentials in both sources): warn once per process.
_warned_both = set()


def _complete(exchange: str, values: Dict[str, str]) -> bool:
    return all(f.name in values for f in secret_fields(exchange) if f.required)


def credential_source(exchange: str) -> Optional[str]:
    """``"environment"``, ``"keyring"`` or None: where a full set would come from."""
    exchange = normalise_exchange(exchange)
    if _complete(exchange, _read_source(exchange, SOURCE_ENV)):
        return SOURCE_ENV
    if _complete(exchange, _read_source(exchange, SOURCE_KEYRING)):
        return SOURCE_KEYRING
    return None


def has_credentials(exchange: str) -> bool:
    return credential_source(exchange) is not None


def get_credentials(exchange: str) -> Optional[Credentials]:
    """The full credential set for ``exchange`` as connector keyword arguments,
    applying the precedence rule, or None when no source holds a full set."""
    exchange = normalise_exchange(exchange)
    env_values = _read_source(exchange, SOURCE_ENV)
    env_ok = _complete(exchange, env_values)
    kr_values = _read_source(exchange, SOURCE_KEYRING)
    kr_ok = _complete(exchange, kr_values)
    if env_ok and kr_ok and exchange not in _warned_both:
        _warned_both.add(exchange)
        logger.warning(
            "Credentials for %s are set both in environment variables and in the OS "
            "keyring; using the environment variables (precedence: environment, then keyring).",
            exchange,
        )
    if env_ok:
        chosen, source = env_values, SOURCE_ENV
    elif kr_ok:
        chosen, source = kr_values, SOURCE_KEYRING
    else:
        return None
    kwargs = {
        f.kwarg: chosen[f.name] for f in secret_fields(exchange) if f.name in chosen
    }
    return Credentials(exchange, source, kwargs)


def stored_fields(exchange: str) -> Tuple[str, ...]:
    """Field names present in the keyring for ``exchange`` (names only)."""
    exchange = normalise_exchange(exchange)
    return tuple(_read_source(exchange, SOURCE_KEYRING))


def redact(text: str, secrets: Iterable[object]) -> str:
    """Replace every occurrence of the given values in ``text`` with ``***``."""
    out = str(text)
    for s in secrets:
        value = s.reveal() if isinstance(s, Secret) else str(s or "")
        if len(value) >= 4:
            out = out.replace(value, REDACTED)
    return out
