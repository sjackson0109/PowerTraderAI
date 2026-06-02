"""Tests for credential rotation and permission validation (issues #58, #59)."""

import json
import os
import shutil
import stat
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from pt_credentials import (
    CredentialMetadata,
    CredentialRotationScheduler,
    PermissionValidator,
    SecureCredentialManager,
    get_credentials,
    validate_credentials_on_startup,
)


class TestCredentialMetadata(unittest.TestCase):
    def test_new_sets_rotation_due_future(self):
        meta = CredentialMetadata.new(90)
        self.assertFalse(meta.is_rotation_due())
        self.assertGreater(meta.days_until_rotation(), 0)

    def test_overdue_when_past_due(self):
        meta = CredentialMetadata(
            created_at=time.time() - 200 * 86400,
            last_rotated_at=time.time() - 200 * 86400,
            rotation_due_at=time.time() - 1,
        )
        self.assertTrue(meta.is_rotation_due())
        self.assertEqual(meta.days_until_rotation(), 0)

    def test_roundtrip_dict(self):
        meta = CredentialMetadata.new(30)
        meta2 = CredentialMetadata.from_dict(meta.to_dict())
        self.assertAlmostEqual(meta.created_at, meta2.created_at, places=3)
        self.assertEqual(meta.rotation_interval_days, meta2.rotation_interval_days)

    def test_from_dict_handles_corrupt_metadata(self):
        """Missing required fields should be caught by _load_metadata."""
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        mgr = SecureCredentialManager(tmpdir)
        # Write partial/corrupt metadata
        with open(mgr.metadata_file, "w") as f:
            json.dump({"created_at": 0}, f)  # missing required fields
        self.assertIsNone(mgr._load_metadata())

    def test_from_dict_raises_value_error_on_missing_fields(self):
        """from_dict must raise ValueError (not opaque TypeError) for missing fields."""
        with self.assertRaises(ValueError):
            CredentialMetadata.from_dict({"created_at": 0})


class TestSecureCredentialManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mgr = SecureCredentialManager(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_encrypt_decrypt_roundtrip(self):
        self.assertTrue(self.mgr.encrypt_credentials("KEY123", "SECRET456"))
        creds = self.mgr.decrypt_credentials()
        self.assertIsNotNone(creds)
        self.assertEqual(creds[0], "KEY123")
        self.assertEqual(creds[1], "SECRET456")

    def test_has_encrypted_after_save(self):
        self.assertFalse(self.mgr.has_encrypted_credentials())
        self.mgr.encrypt_credentials("K", "S")
        self.assertTrue(self.mgr.has_encrypted_credentials())

    def test_metadata_written_on_encrypt(self):
        self.mgr.encrypt_credentials("K", "S", rotation_interval_days=30)
        meta = self.mgr._load_metadata()
        self.assertIsNotNone(meta)
        self.assertEqual(meta.rotation_interval_days, 30)

    def test_metadata_interval_updated_on_reencrypt(self):
        """rotation_interval_days must stay consistent with rotation_due_at."""
        self.mgr.encrypt_credentials("K", "S", rotation_interval_days=30)
        self.mgr.encrypt_credentials("K", "S", rotation_interval_days=60)
        meta = self.mgr._load_metadata()
        self.assertEqual(meta.rotation_interval_days, 60)

    def test_rotation_status_no_metadata(self):
        status = self.mgr.get_rotation_status()
        self.assertFalse(status["has_metadata"])

    def test_rotation_status_with_metadata(self):
        self.mgr.encrypt_credentials("K", "S", rotation_interval_days=90)
        status = self.mgr.get_rotation_status()
        self.assertTrue(status["has_metadata"])
        self.assertFalse(status["rotation_due"])
        self.assertGreater(status["days_until_rotation"], 0)

    def test_rotate_credentials(self):
        self.mgr.encrypt_credentials("OLD_KEY", "OLD_SECRET")
        result = self.mgr.rotate_credentials("NEW_KEY", "NEW_SECRET")
        self.assertTrue(result)
        creds = self.mgr.decrypt_credentials()
        self.assertEqual(creds[0], "NEW_KEY")
        self.assertEqual(creds[1], "NEW_SECRET")

    def test_rotate_cleans_up_backups(self):
        self.mgr.encrypt_credentials("OLD", "OLD")
        self.mgr.rotate_credentials("NEW", "NEW")
        self.assertFalse(os.path.exists(self.mgr.encrypted_key_file + ".bak"))
        self.assertFalse(os.path.exists(self.mgr.encrypted_secret_file + ".bak"))
        self.assertFalse(os.path.exists(self.mgr.metadata_file + ".bak"))

    def test_rotate_restores_metadata_on_failure(self):
        """Rotation rollback must restore metadata alongside ciphertext files."""
        self.mgr.encrypt_credentials("OLD_KEY", "OLD_SECRET", rotation_interval_days=90)
        pre_meta = self.mgr._load_metadata()
        self.assertIsNotNone(pre_meta)

        # Corrupt the manager to force failure during encrypt. Both ciphertexts
        # are staged via _stage_temp_binary; fail the second so the key rename
        # has already committed and rollback must restore the previous key
        # ciphertext.
        original = self.mgr._stage_temp_binary
        call_count = [0]

        def failing_stage(path, data):
            call_count[0] += 1
            if call_count[0] >= 2:  # succeed on key, fail on secret
                raise OSError("disk full")
            return original(path, data)

        self.mgr._stage_temp_binary = failing_stage
        result = self.mgr.rotate_credentials(
            "NEW_KEY", "NEW_SECRET", rotation_interval_days=30
        )
        self.assertFalse(result)
        # Ciphertext: old credentials still decryptable
        creds = self.mgr.decrypt_credentials()
        self.assertEqual(creds[0], "OLD_KEY")
        # Metadata: rotation_interval_days + rotation_due_at unchanged
        post_meta = self.mgr._load_metadata()
        self.assertEqual(
            post_meta.rotation_interval_days, pre_meta.rotation_interval_days
        )
        self.assertEqual(post_meta.rotation_due_at, pre_meta.rotation_due_at)
        self.assertEqual(post_meta.created_at, pre_meta.created_at)

    def test_no_rotation_warning_when_fresh(self):
        self.mgr.encrypt_credentials("K", "S", rotation_interval_days=90)
        self.assertIsNone(self.mgr.check_rotation_warning())

    def test_rotation_warning_when_overdue(self):
        meta = CredentialMetadata(
            created_at=time.time() - 100 * 86400,
            last_rotated_at=time.time() - 100 * 86400,
            rotation_due_at=time.time() - 1,
        )
        self.mgr._save_metadata(meta)
        warning = self.mgr.check_rotation_warning()
        self.assertIsNotNone(warning)
        self.assertIn("OVERDUE", warning)

    def test_rotation_warning_when_near_due(self):
        meta = CredentialMetadata(
            created_at=time.time(),
            last_rotated_at=time.time(),
            rotation_due_at=time.time() + 3 * 86400,
        )
        self.mgr._save_metadata(meta)
        warning = self.mgr.check_rotation_warning()
        self.assertIsNotNone(warning)
        self.assertIn("day", warning)

    def test_legacy_vault_auto_migrates_to_new_derivation(self):
        """
        Vaults encrypted under the legacy COMPUTERNAME/USERNAME derivation
        must decrypt transparently AND be rewritten under the new
        gethostname()/getuser() derivation on the same call, so the legacy
        fallback path is one-shot per vault.
        """
        legacy_pw = "legacy_pw_fixed_for_test_0000000000000000"
        new_pw = "new_pw_fixed_for_test_xxxxxxxxxxxxxxxxxxx"

        # Step 1: encrypt as if the running version were still the legacy build.
        with patch.object(self.mgr, "_get_machine_password", return_value=legacy_pw):
            self.assertTrue(self.mgr.encrypt_credentials("KEY_LEG", "SECRET_LEG"))

        # Sanity: cannot decrypt under new derivation alone (no legacy fallback).
        with patch.object(
            self.mgr, "_get_machine_password", return_value=new_pw
        ), patch.object(self.mgr, "_get_legacy_machine_password", return_value=None):
            self.assertIsNone(self.mgr.decrypt_credentials())

        # Step 2: simulate the upgraded build — primary derivation is new_pw,
        # legacy fallback exposes the same legacy_pw used in step 1.
        with patch.object(
            self.mgr, "_get_machine_password", return_value=new_pw
        ), patch.object(
            self.mgr, "_get_legacy_machine_password", return_value=legacy_pw
        ):
            creds = self.mgr.decrypt_credentials()
            self.assertEqual(creds, ("KEY_LEG", "SECRET_LEG"))

        # Step 3: vault was auto-rewritten under new_pw. Now decrypt with
        # ONLY the new derivation available — legacy fallback returns None —
        # and it must still succeed. Proves the rewrite happened.
        with patch.object(
            self.mgr, "_get_machine_password", return_value=new_pw
        ), patch.object(self.mgr, "_get_legacy_machine_password", return_value=None):
            creds = self.mgr.decrypt_credentials()
            self.assertEqual(creds, ("KEY_LEG", "SECRET_LEG"))

    def test_legacy_migration_preserves_rotation_metadata(self):
        """Derivation migration must NOT reset last_rotated_at /
        rotation_due_at. Without this, a one-shot derivation upgrade would
        masquerade as a real rotation and silently push the next rotation
        warning out by a full interval — defeating the rotation scheduler
        for any vault that triggers the legacy fallback."""
        legacy_pw = "legacy_pw_fixed_for_test_0000000000000000"
        new_pw = "new_pw_fixed_for_test_xxxxxxxxxxxxxxxxxxx"

        # Encrypt under legacy derivation.
        with patch.object(self.mgr, "_get_machine_password", return_value=legacy_pw):
            self.assertTrue(self.mgr.encrypt_credentials("KEY_LEG", "SECRET_LEG"))

        # Backdate metadata so we can detect any reset.
        original = self.mgr._load_metadata()
        self.assertIsNotNone(original)
        backdated_last = time.time() - 30 * 86400  # rotated 30d ago
        backdated_due = time.time() + 60 * 86400  # next due in 60d
        original.last_rotated_at = backdated_last
        original.rotation_due_at = backdated_due
        self.mgr._save_metadata(original)

        # Trigger derivation migration via decrypt path.
        with patch.object(
            self.mgr, "_get_machine_password", return_value=new_pw
        ), patch.object(
            self.mgr, "_get_legacy_machine_password", return_value=legacy_pw
        ):
            self.assertEqual(self.mgr.decrypt_credentials(), ("KEY_LEG", "SECRET_LEG"))

        # Rotation timestamps must be unchanged after the migration.
        migrated = self.mgr._load_metadata()
        self.assertIsNotNone(migrated)
        self.assertAlmostEqual(migrated.last_rotated_at, backdated_last, places=1)
        self.assertAlmostEqual(migrated.rotation_due_at, backdated_due, places=1)

    def test_migrate_from_plaintext(self):
        with open(os.path.join(self.tmpdir, "r_key.txt"), "w") as f:
            f.write("PLAIN_KEY\n")
        with open(os.path.join(self.tmpdir, "r_secret.txt"), "w") as f:
            f.write("PLAIN_SECRET\n")
        result = self.mgr.migrate_from_plaintext()
        self.assertTrue(result)
        self.assertFalse(os.path.exists(os.path.join(self.tmpdir, "r_key.txt")))
        creds = self.mgr.decrypt_credentials()
        self.assertEqual(creds[0], "PLAIN_KEY")

    def test_cross_platform_machine_password(self):
        """machine password should be non-empty on all platforms."""
        pwd = self.mgr._get_machine_password()
        self.assertIsInstance(pwd, str)
        self.assertGreater(len(pwd), 0)


class TestPermissionValidator(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.validator = PermissionValidator(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_fetcher_returns_failed_audit(self):
        result = self.validator.validate(None)
        self.assertFalse(result.audit_passed)
        self.assertFalse(result.has_required)

    def test_all_permissions_granted(self):
        result = self.validator.validate(
            lambda: ["read_account", "read_positions", "buy", "sell"],
            require_trading=True,
        )
        self.assertTrue(result.audit_passed)
        self.assertTrue(result.has_required)
        self.assertTrue(result.has_trading)

    def test_missing_required_permissions(self):
        result = self.validator.validate(
            lambda: ["read_account"],  # missing read_positions
            require_trading=False,
        )
        self.assertFalse(result.audit_passed)
        self.assertIn("read_positions", result.missing_required)

    def test_missing_trading_permissions(self):
        result = self.validator.validate(
            lambda: ["read_account", "read_positions"],
            require_trading=True,
        )
        self.assertFalse(result.audit_passed)
        self.assertFalse(result.has_trading)

    def test_fetcher_exception_handled(self):
        def fetcher():
            raise ConnectionError("API unreachable")

        result = self.validator.validate(fetcher)
        self.assertFalse(result.audit_passed)
        self.assertIn("failed", result.message.lower())

    def test_excess_permissions_warned(self):
        result = self.validator.validate(
            lambda: ["read_account", "read_positions", "buy", "sell", "withdraw"],
            require_trading=True,
        )
        self.assertTrue(result.audit_passed)
        self.assertIn("withdraw", result.excess_permissions)
        self.assertIn("more permissions than required", result.message)

    def test_audit_log_written_and_secured(self):
        self.validator.validate(None)
        log_path = os.path.join(self.tmpdir, PermissionValidator.AUDIT_LOG_FILE)
        self.assertTrue(os.path.exists(log_path))
        with open(log_path) as f:
            entry = json.loads(f.readline())
        self.assertIn("audit_passed", entry)
        # Permission bits: 0600 (user rw only). POSIX-only — chmod is a no-op
        # on Windows so st_mode reflects ACLs, not unix bits.
        if os.name == "posix":
            mode = stat.S_IMODE(os.stat(log_path).st_mode)
            self.assertEqual(mode, stat.S_IRUSR | stat.S_IWUSR)

    def test_audit_history_returned(self):
        self.validator.validate(None)
        history = self.validator.get_audit_history()
        self.assertGreater(len(history), 0)

    def test_audit_log_size_cap(self):
        """Log should not grow past MAX_AUDIT_LINES."""
        # Write many entries manually to reach cap
        log_path = os.path.join(self.tmpdir, PermissionValidator.AUDIT_LOG_FILE)
        entry = json.dumps(
            {
                "audit_passed": False,
                "timestamp": 0,
                "has_required": False,
                "has_trading": False,
                "granted_permissions": [],
                "missing_required": [],
                "missing_trading": [],
                "message": "x",
            }
        )
        with open(log_path, "w") as f:
            for _ in range(PermissionValidator.MAX_AUDIT_LINES + 5):
                f.write(entry + "\n")
        # Trigger a new write, which should trim the file
        self.validator.validate(None)
        with open(log_path) as f:
            lines = f.readlines()
        self.assertLessEqual(len(lines), PermissionValidator.MAX_AUDIT_LINES)


class TestCredentialRotationScheduler(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_start_stop(self):
        cb = MagicMock()
        sched = CredentialRotationScheduler(
            cb, check_interval_hours=24, base_dir=self.tmpdir
        )
        sched.start()
        self.assertTrue(sched._thread.is_alive())
        sched.stop()
        self.assertFalse(sched._thread.is_alive())

    def test_no_callback_without_metadata(self):
        cb = MagicMock()
        sched = CredentialRotationScheduler(
            cb, check_interval_hours=24, base_dir=self.tmpdir
        )
        result = sched.check_now()
        self.assertIsNone(result)
        cb.assert_not_called()

    def test_callback_fires_when_overdue(self):
        """Scheduler must invoke the user callback via _tick() when overdue
        metadata is seeded. Exercises the real callback dispatch path
        (_tick → _run → cb) rather than only the synchronous check_now()
        helper, so a regression that broke the tick→callback wiring would
        be caught here."""
        cb = MagicMock()
        mgr = SecureCredentialManager(self.tmpdir)
        # Seed overdue metadata
        meta = CredentialMetadata(
            created_at=time.time() - 200 * 86400,
            last_rotated_at=time.time() - 200 * 86400,
            rotation_due_at=time.time() - 1,
        )
        mgr._save_metadata(meta)

        sched = CredentialRotationScheduler(
            cb, check_interval_hours=24, base_dir=self.tmpdir
        )

        # check_now() returns the warning string for direct callers.
        warning = sched.check_now()
        self.assertIsNotNone(warning)
        self.assertIn("OVERDUE", warning)

        # _tick() is the scheduler's real dispatch path; it must actually
        # call the callback with the same overdue warning.
        sched._tick()
        cb.assert_called_once()
        (delivered,), _ = cb.call_args
        self.assertIn("OVERDUE", delivered)

    def test_dedup_callback_not_repeated(self):
        """Same warning should not trigger callback twice. Exercises the
        real _tick() path so a regression in dedup logic would fail this test."""
        cb = MagicMock()
        mgr = SecureCredentialManager(self.tmpdir)
        meta = CredentialMetadata(
            created_at=time.time() - 200 * 86400,
            last_rotated_at=time.time() - 200 * 86400,
            rotation_due_at=time.time() - 1,
        )
        mgr._save_metadata(meta)
        sched = CredentialRotationScheduler(
            cb, check_interval_hours=24, base_dir=self.tmpdir
        )

        sched._tick()  # first tick — should fire
        sched._tick()  # second tick — same warning, dedup'd

        cb.assert_called_once()

    def test_tick_fires_on_warning_change(self):
        """When warning text changes, callback fires again."""
        cb = MagicMock()
        mgr = SecureCredentialManager(self.tmpdir)
        sched = CredentialRotationScheduler(
            cb, check_interval_hours=24, base_dir=self.tmpdir
        )

        # Seed overdue → tick should fire
        mgr._save_metadata(
            CredentialMetadata(
                created_at=time.time() - 200 * 86400,
                last_rotated_at=time.time() - 200 * 86400,
                rotation_due_at=time.time() - 1,
            )
        )
        sched._tick()
        self.assertEqual(cb.call_count, 1)

        # Replace with near-due → different message, callback fires again
        mgr._save_metadata(
            CredentialMetadata(
                created_at=time.time(),
                last_rotated_at=time.time(),
                rotation_due_at=time.time() + 3 * 86400,
            )
        )
        sched._tick()
        self.assertEqual(cb.call_count, 2)


class TestStartupCredentialValidation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mgr = SecureCredentialManager(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_startup_rejects_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            ok, msg = validate_credentials_on_startup(base_dir=self.tmpdir)
        self.assertFalse(ok)
        self.assertIn("Missing API credentials", msg)

    def test_startup_rejects_corrupt_vault(self):
        self.assertTrue(self.mgr.encrypt_credentials("KEY123", "SECRET123"))
        with open(self.mgr.encrypted_key_file, "wb") as f:
            f.write(b"corrupted")
        ok, msg = validate_credentials_on_startup(base_dir=self.tmpdir)
        self.assertFalse(ok)
        self.assertIn("unreadable", msg)

    def test_startup_passes_with_valid_vault_without_permission_fetcher(self):
        self.assertTrue(self.mgr.encrypt_credentials("KEY123", "SECRET123"))
        ok, msg = validate_credentials_on_startup(base_dir=self.tmpdir)
        self.assertTrue(ok)
        self.assertIn("Permission validation skipped", msg)

    @patch("pt_credentials.SecureCredentialManager")
    def test_get_credentials_refuses_plaintext_on_failed_migration(self, manager_cls):
        manager = manager_cls.return_value
        manager.has_encrypted_credentials.return_value = False
        manager.has_plaintext_credentials.return_value = True
        manager.migrate_from_plaintext.return_value = False
        self.assertIsNone(get_credentials())


if __name__ == "__main__":
    unittest.main()
