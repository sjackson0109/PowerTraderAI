"""
Secure credential management for PowerTraderAI+.
Handles encryption/decryption of API keys and private keys.
"""
import base64
import hashlib
import os
import stat
from typing import Optional, Tuple

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class SecureCredentialManager:
    """Manages encrypted storage of API credentials."""

    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.salt_file = os.path.join(self.base_dir, ".pt_salt")
        self.encrypted_key_file = os.path.join(self.base_dir, "r_key.enc")
        self.encrypted_secret_file = os.path.join(self.base_dir, "r_secret.enc")

    def _get_or_create_salt(self) -> bytes:
        """Get existing salt or create a new one."""
        if os.path.exists(self.salt_file):
            with open(self.salt_file, "rb") as f:
                return f.read()
        else:
            salt = os.urandom(16)
            self._secure_write_binary(self.salt_file, salt)
            return salt

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password and salt."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def _get_machine_password(self) -> str:
        """Generate a machine-specific password for encryption."""
        # Use machine-specific identifiers for password generation
        machine_info = (
            f"{os.environ.get('COMPUTERNAME', '')}{os.environ.get('USERNAME', '')}"
        )
        return hashlib.sha256(machine_info.encode()).hexdigest()[:32]

    def _secure_write_text(self, filepath: str, content: str) -> None:
        """Write text file with secure permissions."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        self._set_secure_permissions(filepath)

    def _secure_write_binary(self, filepath: str, content: bytes) -> None:
        """Write binary file with secure permissions."""
        with open(filepath, "wb") as f:
            f.write(content)
        self._set_secure_permissions(filepath)

    def _set_secure_permissions(self, filepath: str) -> None:
        """Set file permissions to owner read/write only."""
        try:
            # On Windows, this sets the file to be accessible only by the owner
            os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)
        except (OSError, AttributeError):
            # Fallback for systems that don't support chmod
            pass

    def encrypt_credentials(self, api_key: str, private_key_b64: str) -> bool:
        """Encrypt and save credentials."""
        try:
            salt = self._get_or_create_salt()
            password = self._get_machine_password()
            key = self._derive_key(password, salt)
            cipher = Fernet(key)

            # Encrypt API key
            encrypted_api_key = cipher.encrypt(api_key.encode("utf-8"))
            self._secure_write_binary(self.encrypted_key_file, encrypted_api_key)

            # Encrypt private key
            encrypted_private_key = cipher.encrypt(private_key_b64.encode("utf-8"))
            self._secure_write_binary(self.encrypted_secret_file, encrypted_private_key)

            return True
        except Exception:
            return False

    def decrypt_credentials(self) -> Optional[Tuple[str, str]]:
        """Decrypt and return credentials."""
        try:
            if not (
                os.path.exists(self.encrypted_key_file)
                and os.path.exists(self.encrypted_secret_file)
                and os.path.exists(self.salt_file)
            ):
                return None

            # Load salt
            with open(self.salt_file, "rb") as f:
                salt = f.read()

            password = self._get_machine_password()
            key = self._derive_key(password, salt)
            cipher = Fernet(key)

            # Decrypt API key
            with open(self.encrypted_key_file, "rb") as f:
                encrypted_api_key = f.read()
            api_key = cipher.decrypt(encrypted_api_key).decode("utf-8")

            # Decrypt private key
            with open(self.encrypted_secret_file, "rb") as f:
                encrypted_private_key = f.read()
            private_key_b64 = cipher.decrypt(encrypted_private_key).decode("utf-8")

            return api_key.strip(), private_key_b64.strip()
        except Exception:
            return None

    def migrate_from_plaintext(self) -> bool:
        """Migrate existing plaintext credentials to encrypted format."""
        key_file = os.path.join(self.base_dir, "r_key.txt")
        secret_file = os.path.join(self.base_dir, "r_secret.txt")

        if not (os.path.exists(key_file) and os.path.exists(secret_file)):
            return False

        try:
            # Read plaintext credentials
            with open(key_file, "r", encoding="utf-8") as f:
                api_key = f.read().strip()
            with open(secret_file, "r", encoding="utf-8") as f:
                private_key_b64 = f.read().strip()

            # Encrypt them
            if self.encrypt_credentials(api_key, private_key_b64):
                # Securely delete plaintext files
                try:
                    os.remove(key_file)
                    os.remove(secret_file)
                except OSError:
                    pass
                return True
        except Exception:
            pass
        return False

    def has_encrypted_credentials(self) -> bool:
        """Check if encrypted credentials exist."""
        return (
            os.path.exists(self.encrypted_key_file)
            and os.path.exists(self.encrypted_secret_file)
            and os.path.exists(self.salt_file)
        )

    def has_plaintext_credentials(self) -> bool:
        """Check if plaintext credentials exist."""
        key_file = os.path.join(self.base_dir, "r_key.txt")
        secret_file = os.path.join(self.base_dir, "r_secret.txt")
        return os.path.exists(key_file) and os.path.exists(secret_file)


def get_credentials() -> Optional[Tuple[str, str]]:
    """
    Get API credentials with priority order:
    1. Encrypted credentials (for desktop use)
    2. Environment variables (for CI/CD)
    3. Plaintext files (legacy support)
    Returns (api_key, private_key_b64) or None if not found.
    """
    manager = SecureCredentialManager()

    # Try encrypted credentials first (preferred for desktop)
    if manager.has_encrypted_credentials():
        return manager.decrypt_credentials()

    # Try environment variables (for CI/CD pipelines)
    env_api_key = os.environ.get("POWERTRADER_ROBINHOOD_API_KEY")
    env_private_key = os.environ.get("POWERTRADER_ROBINHOOD_PRIVATE_KEY")

    if env_api_key and env_private_key:
        return env_api_key.strip(), env_private_key.strip()

    # Try to migrate from plaintext
    if manager.has_plaintext_credentials():
        if manager.migrate_from_plaintext():
            return manager.decrypt_credentials()
        else:
            # Fallback to reading plaintext if migration fails
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                with open(
                    os.path.join(base_dir, "r_key.txt"), "r", encoding="utf-8"
                ) as f:
                    api_key = f.read().strip()
                with open(
                    os.path.join(base_dir, "r_secret.txt"), "r", encoding="utf-8"
                ) as f:
                    private_key_b64 = f.read().strip()
                return api_key, private_key_b64
            except Exception:
                pass

    return None
