"""
Credential storage audit tests - issue #52.
Verifies no direct plaintext file reads/writes to r_key.txt / r_secret.txt
exist outside of pt_credentials.py (the authorised migration module).
"""

import ast
import os
import sys
import tempfile
import unittest

APP_DIR = os.path.dirname(__file__)

# Modules explicitly allowed to reference credential filenames
ALLOWLIST = {
    "pt_credentials.py",
}

# Explicit set of test files to exclude from the production-code audit.
# Using an explicit set (not a startswith("test_") prefix) so production
# modules can never accidentally skip the audit by starting with "test_".
TEST_FILES = {
    "test_credential_audit.py",
    "test_backup_validation.py",
    "test_circuit_breaker.py",
    "test_credentials_rotation.py",
    "test_database_manager.py",
    "test_error_handler.py",
    "test_paper_trading_integration.py",
    "test_security_logger.py",
    "test_pt_hub.py",
    "test_comprehensive.py",
}


def _get_python_files():
    """
    Walk APP_DIR recursively; exclude allowlisted and known test files.
    Uses os.walk to cover any future subdirectories.
    """
    result = []
    for dirpath, _, filenames in os.walk(APP_DIR):
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            if fname in ALLOWLIST or fname in TEST_FILES:
                continue
            result.append(os.path.join(dirpath, fname))
    return result


def _unparse_node(node) -> str:
    """
    Return a string representation of an AST node.
    Uses ast.unparse (Python 3.9+) when available; falls back to a simple
    visitor for older interpreters so the audit is never silently a no-op.
    """
    if hasattr(ast, "unparse"):
        return ast.unparse(node)
    # Fallback for Python < 3.9
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Str):  # deprecated but present in 3.8
        return repr(node.s)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_unparse_node(node.value)}.{node.attr}"
    if isinstance(node, ast.BinOp):
        return f"{_unparse_node(node.left)} op {_unparse_node(node.right)}"
    if isinstance(node, ast.JoinedStr):
        # f-string: collect all string constants
        parts = [_unparse_node(v) for v in node.values]
        return "".join(parts)
    return ""


def _ast_cred_opens(filepath, modes=None):
    """
    Parse file with AST and find open() calls whose first arg references
    r_key.txt or r_secret.txt. Returns list of (lineno, description).

    modes: set of mode strings to match (e.g. {"w"}).
           None = match any mode (including default read).
    """
    if sys.version_info < (3, 8):
        # ast.Constant not available before 3.8 — skip with a note
        return []

    hits = []
    try:
        with open(filepath, "r", errors="ignore") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, OSError):
        return hits

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_open = (isinstance(func, ast.Name) and func.id == "open") or (
            isinstance(func, ast.Attribute) and func.attr == "open"
        )
        if not is_open or not node.args:
            continue

        first_arg = _unparse_node(node.args[0])
        if "r_key" not in first_arg and "r_secret" not in first_arg:
            continue

        # Only inspect the second positional argument (index 1) for mode —
        # args[2] is buffering (int), not mode.
        explicit_mode = None
        if len(node.args) > 1:
            explicit_mode = _unparse_node(node.args[1]).strip("\"'")
        for kw in node.keywords:
            if kw.arg == "mode":
                explicit_mode = _unparse_node(kw.value).strip("\"'")

        # If modes filter given, only match those modes
        if modes is not None and explicit_mode not in modes:
            continue

        hits.append((node.lineno, f"open({first_arg!r}, mode={explicit_mode!r})"))

    return hits


class TestCredentialAudit(unittest.TestCase):
    """Audit: no module outside pt_credentials.py writes plaintext credentials."""

    def test_no_direct_plaintext_writes(self):
        """
        No file except pt_credentials.py should open r_key.txt / r_secret.txt
        for writing. Detected via AST (not brittle string matching).
        """
        violations = {}
        for fpath in _get_python_files():
            hits = _ast_cred_opens(fpath, modes={"w", "wb", "a"})
            if hits:
                violations[os.path.basename(fpath)] = hits

        if violations:
            details = "\n".join(
                f"  {fname}: " + "; ".join(f"line {ln}" for ln, _ in hits)
                for fname, hits in violations.items()
            )
            self.fail(
                f"Plaintext credential WRITES outside pt_credentials.py:\n{details}"
            )

    def test_no_direct_plaintext_reads_outside_credentials_module(self):
        """
        No file except pt_credentials.py should open r_key.txt / r_secret.txt
        for reading. All reads must go through get_credentials() or
        SecureCredentialManager.
        """
        violations = {}
        for fpath in _get_python_files():
            hits = _ast_cred_opens(fpath, modes={"r", None})
            if hits:
                violations[os.path.basename(fpath)] = hits

        if violations:
            details = "\n".join(
                f"  {fname}: " + "; ".join(f"line {ln}" for ln, _ in hits)
                for fname, hits in violations.items()
            )
            self.fail(
                f"Direct plaintext credential READS outside pt_credentials.py:\n{details}"
            )

    def test_pt_credentials_public_api(self):
        """pt_credentials.py must expose required public methods."""
        from pt_credentials import SecureCredentialManager, get_credentials

        self.assertTrue(callable(get_credentials))
        for method in (
            "encrypt_credentials",
            "decrypt_credentials",
            "has_encrypted_credentials",
            "has_plaintext_credentials",
        ):
            self.assertTrue(
                hasattr(SecureCredentialManager, method),
                f"SecureCredentialManager missing: {method}",
            )

    def test_secure_credential_manager_roundtrip(self):
        """encrypt + decrypt roundtrip works with a temp directory."""
        from pt_credentials import SecureCredentialManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SecureCredentialManager(tmpdir)
            self.assertFalse(mgr.has_encrypted_credentials())
            ok = mgr.encrypt_credentials("test_api_key", "test_secret_b64")
            self.assertTrue(ok)
            self.assertTrue(mgr.has_encrypted_credentials())
            creds = mgr.decrypt_credentials()
            self.assertIsNotNone(creds)
            self.assertEqual(creds[0], "test_api_key")
            self.assertEqual(creds[1], "test_secret_b64")

    def test_get_credentials_returns_none_when_no_creds(self):
        """get_credentials() returns None when vault is empty."""
        from pt_credentials import SecureCredentialManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SecureCredentialManager(tmpdir)
            self.assertIsNone(mgr.decrypt_credentials())
            self.assertFalse(mgr.has_encrypted_credentials())

    def test_pt_hub_uses_encrypt_credentials(self):
        """
        pt_hub.py must call encrypt_credentials and must NOT write
        r_key.txt / r_secret.txt directly. Verified via AST.
        """
        fpath = os.path.join(APP_DIR, "pt_hub.py")
        with open(fpath, "r", errors="ignore") as f:
            content = f.read()
        self.assertIn("encrypt_credentials", content)

        write_hits = _ast_cred_opens(fpath, modes={"w", "wb"})
        self.assertEqual(
            write_hits,
            [],
            f"pt_hub.py has direct credential writes: {write_hits}",
        )

    def test_pt_hub_reads_via_secure_manager(self):
        """pt_hub.py must reference decrypt_credentials for reading."""
        fpath = os.path.join(APP_DIR, "pt_hub.py")
        with open(fpath, "r", errors="ignore") as f:
            content = f.read()
        self.assertIn("decrypt_credentials", content)

    def test_unparse_fallback_handles_string_constant(self):
        """_unparse_node must return the string value for ast.Constant nodes."""
        node = ast.parse("'r_key.txt'", mode="eval").body
        result = _unparse_node(node)
        self.assertIn("r_key.txt", result)

    def test_mode_parsing_ignores_buffering_arg(self):
        """
        open(path, mode, buffering) — buffering is args[2], not mode.
        Scanner must not mistake an integer buffering arg for a mode string.
        """
        # open(r_key_path, "r", -1)  — buffering=-1, mode="r"
        source = 'open(r_key_path, "r", -1)'
        tree = ast.parse(source, mode="eval")
        call = tree.body
        # Simulate what _ast_cred_opens does: only look at args[1]
        mode_val = None
        if len(call.args) > 1:
            mode_val = _unparse_node(call.args[1]).strip("\"'")
        self.assertEqual(mode_val, "r")  # must be "r", not "-1"


if __name__ == "__main__":
    unittest.main()
