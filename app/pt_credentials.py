"""
Secure credential management for PowerTraderAI+.
Handles encryption/decryption, rotation scheduling, and API permission validation.
"""

import base64
import getpass
import hashlib
import json
import logging
import os
import shutil
import socket
import stat
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


def _get_security_logger():
    """Return SecurityLogger singleton if available, else None."""
    try:
        from pt_security_logger import get_security_logger

        return get_security_logger()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_ROTATION_DAYS = 90
ROTATION_WARNING_DAYS = 7
REQUIRED_PERMISSIONS: Set[str] = {"read_account", "read_positions"}
TRADING_PERMISSIONS: Set[str] = {"buy", "sell"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class CredentialMetadata:
    """Metadata stored alongside encrypted credentials."""

    created_at: float
    last_rotated_at: float
    rotation_due_at: float
    rotation_interval_days: int = DEFAULT_ROTATION_DAYS

    def is_rotation_due(self) -> bool:
        return time.time() >= self.rotation_due_at

    def days_until_rotation(self) -> int:
        return max(0, int((self.rotation_due_at - time.time()) / 86400))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CredentialMetadata":
        """Build from dict. Filters unknown keys; raises ValueError when
        required fields are missing (instead of an opaque TypeError)."""
        required = {"created_at", "last_rotated_at", "rotation_due_at"}
        missing = required - d.keys()
        if missing:
            raise ValueError(
                f"CredentialMetadata missing required fields: {sorted(missing)}"
            )
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def new(cls, interval_days: int = DEFAULT_ROTATION_DAYS) -> "CredentialMetadata":
        now = time.time()
        return cls(
            created_at=now,
            last_rotated_at=now,
            rotation_due_at=now + interval_days * 86400,
            rotation_interval_days=interval_days,
        )


@dataclass
class PermissionAuditResult:
    """Result of an API permission validation check."""

    timestamp: float
    has_required: bool
    has_trading: bool
    granted_permissions: List[str]
    missing_required: List[str]
    missing_trading: List[str]
    audit_passed: bool
    message: str
    excess_permissions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# SecureCredentialManager
# ---------------------------------------------------------------------------
class SecureCredentialManager:
    """Manages encrypted storage and rotation of API credentials."""

    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.salt_file = os.path.join(self.base_dir, ".pt_salt")
        self.encrypted_key_file = os.path.join(self.base_dir, "r_key.enc")
        self.encrypted_secret_file = os.path.join(self.base_dir, "r_secret.enc")
        self.metadata_file = os.path.join(self.base_dir, ".pt_cred_meta")
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_or_create_salt(self) -> bytes:
        if os.path.exists(self.salt_file):
            with open(self.salt_file, "rb") as f:
                return f.read()
        salt = os.urandom(16)
        self._atomic_write_binary(self.salt_file, salt)
        return salt

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def _get_machine_password(self) -> str:
        """
        Cross-platform machine-specific password using hostname + username.
        Avoids Windows-only COMPUTERNAME/USERNAME env vars.
        """
        try:
            host = socket.gethostname()
        except OSError:
            host = ""
        try:
            user = getpass.getuser()
        except OSError:
            user = os.environ.get("USER", os.environ.get("USERNAME", ""))
        return hashlib.sha256(f"{host}{user}".encode()).hexdigest()[:32]

    def _get_legacy_machine_password(self) -> Optional[str]:
        """
        Legacy derivation (Windows-only, pre-cross-platform). Returned only
        when COMPUTERNAME/USERNAME env vars are present so decrypt_credentials
        can fall back transparently for vaults encrypted by older versions.
        """
        host = os.environ.get("COMPUTERNAME")
        user = os.environ.get("USERNAME")
        if not host or not user:
            return None
        return hashlib.sha256(f"{host}{user}".encode()).hexdigest()[:32]

    def _atomic_write_text(self, filepath: str, content: str) -> None:
        """Write text file atomically via unique temp → rename. Uses
        tempfile.mkstemp so concurrent writers cannot collide on the same
        temp name."""
        directory = os.path.dirname(filepath) or "."
        fd, tmp = tempfile.mkstemp(
            prefix=os.path.basename(filepath) + ".", suffix=".tmp", dir=directory
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            self._set_secure_permissions(tmp)
            os.replace(tmp, filepath)
            self._set_secure_permissions(filepath)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    def _stage_temp_binary(self, filepath: str, content: bytes) -> str:
        """Write ``content`` to a sibling temp file and return its path.

        The temp file lives next to ``filepath`` (same filesystem) so the
        subsequent ``os.replace`` is atomic. Caller is responsible for the
        rename or for unlinking on failure.
        """
        directory = os.path.dirname(filepath) or "."
        fd, tmp = tempfile.mkstemp(
            prefix=os.path.basename(filepath) + ".", suffix=".tmp", dir=directory
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
            self._set_secure_permissions(tmp)
            return tmp
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    def _atomic_write_binary(self, filepath: str, content: bytes) -> None:
        """Write binary file atomically via unique temp → rename."""
        tmp = self._stage_temp_binary(filepath, content)
        try:
            os.replace(tmp, filepath)
            self._set_secure_permissions(filepath)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    def _set_secure_permissions(self, filepath: str) -> None:
        try:
            os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)
        except (OSError, AttributeError):
            pass

    # ------------------------------------------------------------------
    # Metadata management
    # ------------------------------------------------------------------
    def _load_metadata(self) -> Optional[CredentialMetadata]:
        if not os.path.exists(self.metadata_file):
            return None
        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                return CredentialMetadata.from_dict(json.load(f))
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            return None

    def _save_metadata(self, meta: CredentialMetadata) -> None:
        self._atomic_write_text(
            self.metadata_file, json.dumps(meta.to_dict(), indent=2)
        )

    # ------------------------------------------------------------------
    # Core encrypt / decrypt
    # ------------------------------------------------------------------
    def encrypt_credentials(
        self,
        api_key: str,
        private_key_b64: str,
        rotation_interval_days: int = DEFAULT_ROTATION_DAYS,
    ) -> bool:
        """
        Encrypt and persist credentials atomically.

        Two-phase commit: both ciphertexts are written to temp files first and
        only then renamed into place. If the second os.replace fails after the
        first has already swapped the key file, the previously-saved key file
        is restored from an in-process backup so the vault never ends up with
        a new key ciphertext paired with the old secret ciphertext.
        """
        with self._lock:
            try:
                salt = self._get_or_create_salt()
                key = self._derive_key(self._get_machine_password(), salt)
                cipher = Fernet(key)

                key_ct = cipher.encrypt(api_key.encode("utf-8"))
                secret_ct = cipher.encrypt(private_key_b64.encode("utf-8"))

                # Phase 1: stage both ciphertexts on disk before committing
                # either. If staging fails for one, neither gets renamed in.
                key_tmp = self._stage_temp_binary(self.encrypted_key_file, key_ct)
                try:
                    secret_tmp = self._stage_temp_binary(
                        self.encrypted_secret_file, secret_ct
                    )
                except Exception:
                    try:
                        os.remove(key_tmp)
                    except OSError:
                        pass
                    raise

                # Phase 2: commit both. If the second commit fails after the
                # first has swapped the key file, restore the previous key
                # ciphertext from a snapshot kept in memory.
                prev_key_blob: Optional[bytes] = None
                if os.path.exists(self.encrypted_key_file):
                    try:
                        with open(self.encrypted_key_file, "rb") as _f:
                            prev_key_blob = _f.read()
                    except OSError:
                        prev_key_blob = None

                try:
                    os.replace(key_tmp, self.encrypted_key_file)
                    self._set_secure_permissions(self.encrypted_key_file)
                except Exception:
                    try:
                        os.remove(key_tmp)
                    except OSError:
                        pass
                    try:
                        os.remove(secret_tmp)
                    except OSError:
                        pass
                    raise

                try:
                    os.replace(secret_tmp, self.encrypted_secret_file)
                    self._set_secure_permissions(self.encrypted_secret_file)
                except Exception:
                    # Roll the key file back so callers don't see a mismatched
                    # ciphertext pair after we return False.
                    if prev_key_blob is not None:
                        try:
                            with open(self.encrypted_key_file, "wb") as _f:
                                _f.write(prev_key_blob)
                            self._set_secure_permissions(self.encrypted_key_file)
                        except OSError:
                            logger.error(
                                "Rollback of key ciphertext failed after secret "
                                "write error; vault may be inconsistent"
                            )
                    try:
                        os.remove(secret_tmp)
                    except OSError:
                        pass
                    raise

                # Update metadata — keep interval consistent
                existing = self._load_metadata()
                now = time.time()
                if existing:
                    existing.last_rotated_at = now
                    existing.rotation_due_at = now + rotation_interval_days * 86400
                    existing.rotation_interval_days = (
                        rotation_interval_days  # keep consistent
                    )
                    meta = existing
                else:
                    meta = CredentialMetadata.new(rotation_interval_days)
                self._save_metadata(meta)

                logger.info("Credentials encrypted and saved successfully")
                return True
            except Exception as exc:
                logger.error("Failed to encrypt credentials: %s", exc)
                return False

    def decrypt_credentials(self) -> Optional[Tuple[str, str]]:
        """Decrypt and return (api_key, private_key_b64), or None on failure.

        Falls back to the legacy COMPUTERNAME/USERNAME derivation if the new
        gethostname()/getuser() derivation fails — this allows vaults encrypted
        by pre-cross-platform versions to decrypt without user intervention.
        On successful legacy decrypt, re-encrypts with the new key so the
        fallback is one-shot per vault.
        """
        with self._lock:
            if not self.has_encrypted_credentials():
                return None
            try:
                with open(self.salt_file, "rb") as f:
                    salt = f.read()
                with open(self.encrypted_key_file, "rb") as f:
                    key_blob = f.read()
                with open(self.encrypted_secret_file, "rb") as f:
                    secret_blob = f.read()
            except OSError as exc:
                logger.error("Failed to read vault files: %s", exc)
                return None

            # Try current derivation first
            try:
                cipher = Fernet(self._derive_key(self._get_machine_password(), salt))
                api_key = cipher.decrypt(key_blob).decode("utf-8").strip()
                private_key = cipher.decrypt(secret_blob).decode("utf-8").strip()
                sec_logger = _get_security_logger()
                if sec_logger is not None:
                    sec_logger.log_credential_use("robinhood", "decrypt_credentials")
                return api_key, private_key
            except Exception as exc:
                logger.debug(
                    "Primary decrypt failed, trying legacy derivation: %s", exc
                )

            # Fallback: legacy Windows derivation
            legacy_pw = self._get_legacy_machine_password()
            if legacy_pw is None:
                logger.error("Failed to decrypt credentials with current derivation")
                return None
            try:
                cipher = Fernet(self._derive_key(legacy_pw, salt))
                api_key = cipher.decrypt(key_blob).decode("utf-8").strip()
                private_key = cipher.decrypt(secret_blob).decode("utf-8").strip()
            except Exception as exc:
                logger.error("Failed to decrypt credentials (legacy fallback): %s", exc)
                return None

            logger.warning(
                "Decrypted vault using legacy machine-password derivation. "
                "Re-encrypting with new derivation."
            )
            # Snapshot rotation metadata so the derivation migration does not
            # masquerade as a real credential rotation. encrypt_credentials()
            # otherwise resets last_rotated_at / rotation_due_at and would
            # silently push the next rotation warning out by a full interval.
            prior_meta = self._load_metadata()
            try:
                if self.encrypt_credentials(api_key, private_key) and prior_meta:
                    refreshed = self._load_metadata()
                    if refreshed is not None:
                        refreshed.last_rotated_at = prior_meta.last_rotated_at
                        refreshed.rotation_due_at = prior_meta.rotation_due_at
                        refreshed.rotation_interval_days = (
                            prior_meta.rotation_interval_days
                        )
                        refreshed.created_at = prior_meta.created_at
                        self._save_metadata(refreshed)
            except Exception as exc:
                logger.warning("Re-encrypt after legacy decrypt failed: %s", exc)
            sec_logger = _get_security_logger()
            if sec_logger is not None:
                sec_logger.log_credential_use(
                    "robinhood",
                    "decrypt_credentials_legacy_migration",
                )
            return api_key, private_key

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------
    def get_rotation_status(self) -> Dict[str, Any]:
        """Return a dict with a consistent shape regardless of metadata
        presence (all keys always present; None when not applicable)."""
        meta = self._load_metadata()
        if not meta:
            return {
                "has_metadata": False,
                "rotation_due": False,
                "days_until_rotation": None,
                "last_rotated_at": None,
                "rotation_due_at": None,
            }
        return {
            "has_metadata": True,
            "rotation_due": meta.is_rotation_due(),
            "days_until_rotation": meta.days_until_rotation(),
            "last_rotated_at": datetime.fromtimestamp(meta.last_rotated_at).isoformat(),
            "rotation_due_at": datetime.fromtimestamp(meta.rotation_due_at).isoformat(),
        }

    def rotate_credentials(
        self,
        new_api_key: str,
        new_private_key_b64: str,
        rotation_interval_days: int = DEFAULT_ROTATION_DAYS,
    ) -> bool:
        """
        Gracefully rotate credentials with full rollback on failure.
        Backs up key, secret, AND metadata so all three are restored together.
        """
        with self._lock:
            backup_key = self.encrypted_key_file + ".bak"
            backup_secret = self.encrypted_secret_file + ".bak"
            backup_meta = self.metadata_file + ".bak"
            backed_up = False

            # Snapshot created_at before rotation so it is never silently reset.
            # encrypt_credentials() constructs new metadata (resetting created_at)
            # when the metadata file is missing or corrupt at rotation time.
            prior_created_at: Optional[float] = None
            prior_meta = self._load_metadata()
            if prior_meta is not None:
                prior_created_at = prior_meta.created_at

            try:
                if self.has_encrypted_credentials():
                    shutil.copy2(self.encrypted_key_file, backup_key)
                    shutil.copy2(self.encrypted_secret_file, backup_secret)
                    if os.path.exists(self.metadata_file):
                        shutil.copy2(self.metadata_file, backup_meta)
                    backed_up = True

                if self.encrypt_credentials(
                    new_api_key, new_private_key_b64, rotation_interval_days
                ):
                    # Restore original created_at if encrypt_credentials reset it
                    if prior_created_at is not None:
                        meta = self._load_metadata()
                        if meta is not None and meta.created_at != prior_created_at:
                            meta.created_at = prior_created_at
                            self._save_metadata(meta)

                    for f in (backup_key, backup_secret, backup_meta):
                        try:
                            os.remove(f)
                        except OSError:
                            pass
                    logger.info("Credentials rotated successfully")
                    sec_logger = _get_security_logger()
                    if sec_logger is not None:
                        sec_logger.log_credential_rotation("robinhood", True)
                    return True

                raise RuntimeError("encrypt_credentials returned False")

            except Exception as exc:
                logger.error("Credential rotation failed: %s", exc)
                sec_logger = _get_security_logger()
                if sec_logger is not None:
                    sec_logger.log_credential_rotation(
                        "robinhood",
                        False,
                        details={"error": str(exc)},
                    )
                if backed_up:
                    try:
                        # os.replace is atomic (POSIX rename): no partial-restore window
                        os.replace(backup_key, self.encrypted_key_file)
                        os.replace(backup_secret, self.encrypted_secret_file)
                        if os.path.exists(backup_meta):
                            os.replace(backup_meta, self.metadata_file)
                        logger.info("Rolled back to previous credentials")
                    except OSError as restore_exc:
                        logger.critical(
                            "CRITICAL: Failed to restore credentials after rotation failure: %s",
                            restore_exc,
                        )
                return False

    def check_rotation_warning(self) -> Optional[str]:
        """Return a warning string if rotation due soon/overdue, else None."""
        status = self.get_rotation_status()
        if not status["has_metadata"]:
            return None
        days = status["days_until_rotation"]
        if status["rotation_due"]:
            return (
                f"SECURITY WARNING: API credentials rotation is OVERDUE. "
                f"Last rotated: {status['last_rotated_at']}. Please rotate immediately."
            )
        if days is not None and days <= ROTATION_WARNING_DAYS:
            return (
                f"SECURITY NOTICE: API credentials rotation due in {days} day(s). "
                f"Due at: {status['rotation_due_at']}."
            )
        return None

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------
    def migrate_from_plaintext(self) -> bool:
        """Migrate existing plaintext r_key.txt / r_secret.txt to encrypted."""
        key_file = os.path.join(self.base_dir, "r_key.txt")
        secret_file = os.path.join(self.base_dir, "r_secret.txt")
        if not (os.path.exists(key_file) and os.path.exists(secret_file)):
            return False
        try:
            with open(key_file, "r", encoding="utf-8") as f:
                api_key = f.read().strip()
            with open(secret_file, "r", encoding="utf-8") as f:
                private_key = f.read().strip()
            if self.encrypt_credentials(api_key, private_key):
                for path in (key_file, secret_file):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                logger.info("Migrated plaintext credentials to encrypted storage")
                return True
        except Exception as exc:
            logger.error("Plaintext migration failed: %s", exc)
        return False

    # ------------------------------------------------------------------
    # State checks
    # ------------------------------------------------------------------
    def has_encrypted_credentials(self) -> bool:
        return all(
            os.path.exists(p)
            for p in (
                self.encrypted_key_file,
                self.encrypted_secret_file,
                self.salt_file,
            )
        )

    def has_plaintext_credentials(self) -> bool:
        return all(
            os.path.exists(os.path.join(self.base_dir, f))
            for f in ("r_key.txt", "r_secret.txt")
        )


# ---------------------------------------------------------------------------
# PermissionValidator
# ---------------------------------------------------------------------------
class PermissionValidator:
    """Validates API key permissions on startup against required permission sets.

    Note on default base_dir: resolves to the source directory of this module
    when not supplied. For production installs to read-only locations, pass a
    writable base_dir explicitly (e.g. user data dir).
    """

    AUDIT_LOG_FILE = "credential_audit.jsonl"
    MAX_AUDIT_LINES = 10_000  # Soft cap; older entries rotated to .1
    AUDIT_ROTATION_KEEP = 1  # Number of rotated backups to keep

    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self._audit_log = os.path.join(self.base_dir, self.AUDIT_LOG_FILE)

    def validate(
        self,
        permission_fetcher: Optional[Callable[[], List[str]]] = None,
        require_trading: bool = False,
    ) -> PermissionAuditResult:
        """
        Validate API permissions.

        Args:
            permission_fetcher: Callable → list of permission strings.
                                If None, returns failed audit (offline/CI use).
            require_trading: Also check for buy/sell permissions.
        """
        now = time.time()

        if permission_fetcher is None:
            result = PermissionAuditResult(
                timestamp=now,
                has_required=False,
                has_trading=False,
                granted_permissions=[],
                missing_required=sorted(REQUIRED_PERMISSIONS),
                missing_trading=(
                    sorted(TRADING_PERMISSIONS) if require_trading else []
                ),
                audit_passed=False,
                message=(
                    "No permission fetcher provided — unable to validate API permissions. "
                    "Provide a permission_fetcher callable to enable validation."
                ),
            )
            self._log_audit(result)
            return result

        try:
            granted = set(permission_fetcher())
        except Exception as exc:
            result = PermissionAuditResult(
                timestamp=now,
                has_required=False,
                has_trading=False,
                granted_permissions=[],
                missing_required=sorted(REQUIRED_PERMISSIONS),
                missing_trading=(
                    sorted(TRADING_PERMISSIONS) if require_trading else []
                ),
                audit_passed=False,
                message=f"Permission fetch failed: {exc}",
            )
            self._log_audit(result)
            logger.error("API permission validation failed: %s", exc)
            return result

        missing_required = sorted(REQUIRED_PERMISSIONS - granted)
        missing_trading = (
            sorted(TRADING_PERMISSIONS - granted) if require_trading else []
        )
        required_now = set(REQUIRED_PERMISSIONS)
        if require_trading:
            required_now |= TRADING_PERMISSIONS
        excess_permissions = sorted(granted - required_now)
        has_required = len(missing_required) == 0
        has_trading = len(missing_trading) == 0
        audit_passed = has_required and (has_trading if require_trading else True)

        if audit_passed:
            message = "API permission validation passed."
        elif not has_required:
            message = (
                f"SECURITY ALERT: API key is missing required permissions: "
                f"{missing_required}. Trading is disabled."
            )
            logger.critical(message)
        else:
            message = (
                f"WARNING: API key is missing trading permissions: {missing_trading}. "
                f"Live trading will be unavailable."
            )
            logger.warning(message)
        if excess_permissions:
            compliance = (
                f"PERMISSION COMPLIANCE WARNING: API key has more permissions than "
                f"required: {excess_permissions}. Least-privilege is recommended."
            )
            logger.warning(compliance)
            message = f"{message} {compliance}"

        result = PermissionAuditResult(
            timestamp=now,
            has_required=has_required,
            has_trading=has_trading,
            granted_permissions=sorted(granted),
            missing_required=missing_required,
            missing_trading=missing_trading,
            excess_permissions=excess_permissions,
            audit_passed=audit_passed,
            message=message,
        )
        self._log_audit(result)
        self._log_security_audit(result)
        return result

    def _log_security_audit(self, result: PermissionAuditResult) -> None:
        sec_logger = _get_security_logger()
        if sec_logger is None:
            return
        sec_logger.log_credential_use("robinhood", "permission_validation")
        for permission in result.missing_required + result.missing_trading:
            sec_logger.log_permission_denied(
                "robinhood",
                permission,
                details={"granted_permissions": result.granted_permissions},
            )
        if result.excess_permissions:
            sec_logger.log_permission_compliance_warning(
                "robinhood",
                result.excess_permissions,
            )

    def _log_audit(self, result: PermissionAuditResult) -> None:
        """Append audit result to JSONL log. Rotates when MAX_AUDIT_LINES is
        reached (renames active log to ``*.1``, drops older rotations). This
        avoids the per-call O(n) read/rewrite of the previous trim strategy."""
        try:
            self._rotate_audit_if_needed()
            with open(self._audit_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(result.to_dict()) + "\n")
            try:
                os.chmod(self._audit_log, stat.S_IRUSR | stat.S_IWUSR)
            except (OSError, AttributeError):
                pass
        except OSError as exc:
            logger.warning("Could not write permission audit log: %s", exc)

    def _rotate_audit_if_needed(self) -> None:
        """Rotate audit log when line count reaches MAX_AUDIT_LINES.

        Uses size-based heuristic to avoid reading the file every call: only
        counts lines if the file is large enough to plausibly hit the cap.
        Approximate entry size is ~200 bytes; we trigger the precise check
        once the file exceeds MAX_AUDIT_LINES * 100 bytes.
        """
        try:
            size = os.path.getsize(self._audit_log)
        except OSError:
            return
        if size < self.MAX_AUDIT_LINES * 100:
            return  # cheap path: nowhere near the cap
        try:
            with open(self._audit_log, "rb") as f:
                line_count = sum(1 for _ in f)
        except OSError:
            return
        if line_count < self.MAX_AUDIT_LINES:
            return
        # Rotate: shift active → .1 → .2 → ... keep at most AUDIT_ROTATION_KEEP
        # backups. Older generations are discarded.
        keep = max(1, int(self.AUDIT_ROTATION_KEEP))
        try:
            # Drop the oldest generation beyond the retention window.
            oldest = f"{self._audit_log}.{keep}"
            if os.path.exists(oldest):
                os.remove(oldest)
            # Shift down: .N-1 → .N, ..., .1 → .2
            for i in range(keep - 1, 0, -1):
                src = f"{self._audit_log}.{i}"
                dst = f"{self._audit_log}.{i + 1}"
                if os.path.exists(src):
                    os.replace(src, dst)
            # Active log → .1
            rotated = f"{self._audit_log}.1"
            os.replace(self._audit_log, rotated)
            try:
                os.chmod(rotated, stat.S_IRUSR | stat.S_IWUSR)
            except (OSError, AttributeError):
                pass
        except OSError as exc:
            logger.warning("Audit log rotation failed: %s", exc)

    def get_audit_history(self, limit: int = 50) -> List[dict]:
        if not os.path.exists(self._audit_log):
            return []
        try:
            with open(self._audit_log, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return [json.loads(line) for line in lines[-limit:] if line.strip()]
        except (OSError, json.JSONDecodeError):
            return []


# ---------------------------------------------------------------------------
# CredentialRotationScheduler
# ---------------------------------------------------------------------------
class CredentialRotationScheduler:
    """
    Background scheduler: checks rotation status periodically and fires a
    notification callback when action is needed.

    De-duplicates notifications — only calls the callback when the warning
    message changes, preventing repeated identical alerts on every tick while
    credentials remain overdue.
    """

    MIN_INTERVAL_SECONDS = 60  # Lower bound on tick interval

    def __init__(
        self,
        notification_callback: Callable[[str], None],
        check_interval_hours: float = 24.0,
        base_dir: str = None,
    ):
        self._callback = notification_callback
        raw_interval = check_interval_hours * 3600
        self._interval = max(raw_interval, self.MIN_INTERVAL_SECONDS)
        if raw_interval < self.MIN_INTERVAL_SECONDS:
            logger.warning(
                "check_interval_hours=%.4f clamped to %ds minimum",
                check_interval_hours,
                self.MIN_INTERVAL_SECONDS,
            )
        self._manager = SecureCredentialManager(base_dir)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_warning: Optional[str] = None  # de-dup tracker

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="CredentialRotationScheduler", daemon=True
        )
        self._thread.start()
        logger.info(
            "Credential rotation scheduler started (interval: %.1fh)",
            self._interval / 3600,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.warning(
                    "Credential rotation scheduler thread did not exit within 5s"
                )
                return
        logger.info("Credential rotation scheduler stopped")

    def _tick(self) -> None:
        """Single check + dedup-callback cycle. Extracted so tests can exercise
        the real dedup path without simulating it.

        ``_last_warning`` is updated *before* the callback fires so a failing
        callback does not cause the scheduler to re-fire the same warning on
        every subsequent tick. Callback exceptions are logged and isolated."""
        try:
            warning = self._manager.check_rotation_warning()
        except Exception as exc:
            logger.error("Rotation scheduler check failed: %s", exc)
            return
        if warning and warning != self._last_warning:
            logger.warning(warning)
            # Update dedup state first so a callback exception cannot cause
            # the same warning to be re-fired on every subsequent tick.
            self._last_warning = warning
            try:
                self._callback(warning)
            except Exception as cb_exc:
                logger.error(
                    "Rotation notification callback raised: %s", cb_exc, exc_info=True
                )
            return
        self._last_warning = warning

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._tick()
            self._stop_event.wait(timeout=self._interval)

    def check_now(self) -> Optional[str]:
        """Immediate one-shot check. Returns warning string or None."""
        return self._manager.check_rotation_warning()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_credentials() -> Optional[Tuple[str, str]]:
    """
    Get API credentials with priority:
    1. Encrypted vault
    2. Environment variables (CI/CD)
    3. Auto-migrate from plaintext (last resort — also preserves plaintext
       fallback if vault write fails, to prevent user lockout)

    Returns (api_key, private_key_b64) or None.
    """
    manager = SecureCredentialManager()
    sec_logger = _get_security_logger()
    if sec_logger is None:
        logger.warning(
            "Security logger unavailable; credential access events will not be "
            "recorded in security_audit.jsonl."
        )

    if manager.has_encrypted_credentials():
        creds = manager.decrypt_credentials()
        if sec_logger is not None:
            if creds:
                sec_logger.log_credential_use("robinhood", "get_credentials_vault")
            else:
                sec_logger.log_auth_attempt(
                    "robinhood",
                    False,
                    details={"operation": "get_credentials_vault"},
                )
        return creds

    env_key = os.environ.get("POWERTRADER_ROBINHOOD_API_KEY")
    env_secret = os.environ.get("POWERTRADER_ROBINHOOD_PRIVATE_KEY")
    if env_key and env_secret:
        if sec_logger is not None:
            sec_logger.log_credential_use("robinhood", "get_credentials_environment")
        return env_key.strip(), env_secret.strip()

    if manager.has_plaintext_credentials():
        if manager.migrate_from_plaintext():
            creds = manager.decrypt_credentials()
            if sec_logger is not None:
                if creds:
                    sec_logger.log_credential_use(
                        "robinhood", "get_credentials_migrated"
                    )
                else:
                    sec_logger.log_auth_attempt(
                        "robinhood",
                        False,
                        details={"operation": "get_credentials_migrated"},
                    )
            return creds
        logger.error(
            "SECURITY ALERT: Plaintext credentials were detected but migration "
            "to encrypted storage failed. Refusing to use plaintext credentials."
        )
        return None

    return None


def validate_credentials_on_startup(
    permission_fetcher: Optional[Callable[[], List[str]]] = None,
    require_trading: bool = True,
    notify_rotation: Optional[Callable[[str], None]] = None,
    base_dir: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Startup validation: checks permission audit AND rotation status.

    Args:
        base_dir: Override the default base directory for the credential
            vault and audit log. Useful for tests and non-default installs.

    Returns:
        (audit_passed: bool, message: str)
    """
    manager = SecureCredentialManager(base_dir)
    validator = PermissionValidator(base_dir)
    messages = []
    sec_logger = _get_security_logger()
    if sec_logger is None:
        logger.warning(
            "Security logger unavailable during startup validation; credential "
            "access audit events will not be recorded."
        )

    env_key = os.environ.get("POWERTRADER_ROBINHOOD_API_KEY")
    env_secret = os.environ.get("POWERTRADER_ROBINHOOD_PRIVATE_KEY")
    has_env_credentials = bool(env_key and env_secret)

    if manager.has_encrypted_credentials():
        creds = manager.decrypt_credentials()
        if creds is None:
            return (
                False,
                "SECURITY ALERT: Encrypted credential vault is present but unreadable "
                "or corrupt. Startup rejected.",
            )
        api_key, private_key = creds
        if not api_key or not private_key:
            return (
                False,
                "SECURITY ALERT: Encrypted credential vault is present but unreadable "
                "or corrupt. Startup rejected.",
            )
        if sec_logger is not None:
            sec_logger.log_credential_use("robinhood", "startup_validation_vault")
    elif manager.has_plaintext_credentials():
        if not manager.migrate_from_plaintext():
            return (
                False,
                "SECURITY ALERT: Plaintext credentials detected but migration failed. "
                "Startup rejected to avoid insecure credential use.",
            )
        creds = manager.decrypt_credentials()
        if not creds:
            return (
                False,
                "SECURITY ALERT: Plaintext migration completed but encrypted vault "
                "could not be read. Startup rejected.",
            )
        if sec_logger is not None:
            sec_logger.log_credential_use("robinhood", "startup_validation_migrated")
    elif not has_env_credentials:
        return (
            False,
            "SECURITY ALERT: Missing API credentials. Configure encrypted credentials "
            "or set POWERTRADER_ROBINHOOD_API_KEY / POWERTRADER_ROBINHOOD_PRIVATE_KEY.",
        )
    elif sec_logger is not None:
        sec_logger.log_credential_use("robinhood", "startup_validation_environment")

    warning = manager.check_rotation_warning()
    if warning:
        messages.append(warning)
        if notify_rotation:
            notify_rotation(warning)

    if permission_fetcher is None:
        skip_msg = "Permission validation skipped: no permission_fetcher provided."
        logger.warning(skip_msg)
        messages.append(skip_msg)
        audit_passed = True
    else:
        audit = validator.validate(permission_fetcher, require_trading)
        messages.append(audit.message)
        audit_passed = audit.audit_passed

    return audit_passed, " | ".join(messages)
