"""
Secure file operations for PowerTraderAI+.
Provides secure file writing with proper permissions.
"""
import json
import os
import stat
import tempfile
from typing import Any, Dict


def secure_write_text(filepath: str, content: str, encoding: str = "utf-8") -> bool:
    """
    Write text content to file with secure permissions.

    Args:
        filepath: Path to the file
        content: Text content to write
        encoding: File encoding (default: utf-8)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Write to temporary file first, then move (atomic operation)
        temp_file = None
        with tempfile.NamedTemporaryFile(
            mode="w", encoding=encoding, delete=False, dir=os.path.dirname(filepath)
        ) as f:
            temp_file = f.name
            f.write(content)

        # Move temporary file to final location
        if os.path.exists(filepath):
            os.remove(filepath)
        os.rename(temp_file, filepath)

        # Set secure permissions
        set_secure_permissions(filepath)
        return True

    except Exception:
        # Clean up temporary file if something went wrong
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        return False


def secure_write_json(filepath: str, data: Any, encoding: str = "utf-8") -> bool:
    """
    Write JSON data to file with secure permissions.

    Args:
        filepath: Path to the file
        data: Data to serialize as JSON
        encoding: File encoding (default: utf-8)

    Returns:
        True if successful, False otherwise
    """
    try:
        json_content = json.dumps(data, indent=2, ensure_ascii=False)
        return secure_write_text(filepath, json_content, encoding)
    except Exception:
        return False


def secure_append_text(filepath: str, content: str, encoding: str = "utf-8") -> bool:
    """
    Append text content to file with secure permissions.

    Args:
        filepath: Path to the file
        content: Text content to append
        encoding: File encoding (default: utf-8)

    Returns:
        True if successful, False otherwise
    """
    try:
        # For append operations, we need to be more careful about atomicity
        existing_content = ""
        if os.path.exists(filepath):
            with open(filepath, "r", encoding=encoding) as f:
                existing_content = f.read()

        new_content = existing_content + content
        return secure_write_text(filepath, new_content, encoding)

    except Exception:
        return False


def set_secure_permissions(filepath: str) -> bool:
    """
    Set secure file permissions (owner read/write only).

    Args:
        filepath: Path to the file

    Returns:
        True if successful, False otherwise
    """
    try:
        # Set owner read/write only
        os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)
        return True
    except (OSError, AttributeError):
        # Some systems may not support chmod or may have different permission models
        return False


def ensure_secure_directory(dirpath: str) -> bool:
    """
    Ensure directory exists with secure permissions.

    Args:
        dirpath: Path to the directory

    Returns:
        True if successful, False otherwise
    """
    try:
        if not os.path.exists(dirpath):
            os.makedirs(dirpath, mode=0o700)  # Owner read/write/execute only
        else:
            # Update permissions on existing directory
            os.chmod(dirpath, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        return True
    except (OSError, AttributeError):
        return False


def secure_read_text(filepath: str, encoding: str = "utf-8") -> str:
    """
    Safely read text file with input validation.

    Args:
        filepath: Path to the file
        encoding: File encoding (default: utf-8)

    Returns:
        File content or empty string on error
    """
    try:
        # Validate file path
        if not os.path.isfile(filepath):
            return ""

        # Check if file is too large (prevent memory exhaustion)
        file_size = os.path.getsize(filepath)
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            return ""

        with open(filepath, "r", encoding=encoding, errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def secure_read_json(filepath: str, encoding: str = "utf-8") -> Dict[str, Any]:
    """
    Safely read JSON file with validation.

    Args:
        filepath: Path to the file
        encoding: File encoding (default: utf-8)

    Returns:
        Parsed JSON data or empty dict on error
    """
    try:
        content = secure_read_text(filepath, encoding)
        if not content:
            return {}
        return json.loads(content)
    except Exception:
        return {}


def validate_file_path(filepath: str, allowed_dirs: list = None) -> bool:
    """
    Validate that file path is safe and within allowed directories.

    Args:
        filepath: Path to validate
        allowed_dirs: List of allowed directory paths (default: current directory)

    Returns:
        True if path is safe, False otherwise
    """
    try:
        # Resolve path to prevent directory traversal
        abs_path = os.path.abspath(filepath)

        # Default to current working directory if no allowed dirs specified
        if allowed_dirs is None:
            allowed_dirs = [os.getcwd()]

        # Check if path is within allowed directories
        for allowed_dir in allowed_dirs:
            abs_allowed = os.path.abspath(allowed_dir)
            if abs_path.startswith(abs_allowed + os.sep) or abs_path == abs_allowed:
                return True

        return False
    except Exception:
        return False
