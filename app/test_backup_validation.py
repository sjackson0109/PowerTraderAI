"""Tests for pt_backup (issue #62) and DataIntegrityValidator (issue #63)."""

import os
import sqlite3
import tempfile
import time
import unittest

from pt_backup import DatabaseBackupManager
from pt_validation import DataIntegrityValidator


# ---------------------------------------------------------------------------
# pt_backup tests
# ---------------------------------------------------------------------------
def _make_test_db(path: str) -> None:
    """Create a minimal SQLite DB for testing."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, symbol TEXT, amount REAL)"
    )
    conn.execute("INSERT INTO orders VALUES (1, 'BTC-USD', 0.5)")
    conn.commit()
    conn.close()


class TestDatabaseBackupManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.backup_dir = os.path.join(self.tmpdir, "backups")
        _make_test_db(self.db_path)
        self.mgr = DatabaseBackupManager(
            db_path=self.db_path,
            backup_dir=self.backup_dir,
            max_backups=5,
        )

    def test_creates_backup(self):
        record = self.mgr.create_backup()
        self.assertIsNotNone(record)
        self.assertTrue(os.path.exists(record.backup_path))

    def test_backup_has_checksum(self):
        record = self.mgr.create_backup()
        self.assertTrue(len(record.sha256_checksum) == 64)

    def test_backup_integrity_check_passes(self):
        record = self.mgr.create_backup()
        self.assertTrue(record.integrity_check_passed)

    def test_verify_backup_clean(self):
        record = self.mgr.create_backup()
        self.assertTrue(self.mgr.verify_backup(record.backup_id))

    def test_verify_backup_detects_tamper(self):
        record = self.mgr.create_backup()
        # Corrupt backup file
        with open(record.backup_path, "ab") as f:
            f.write(b"CORRUPTED")
        self.assertFalse(self.mgr.verify_backup(record.backup_id))

    def test_verify_missing_backup(self):
        self.assertFalse(self.mgr.verify_backup("nonexistent_backup"))

    def test_list_backups(self):
        self.mgr.create_backup()
        self.mgr.create_backup()
        records = self.mgr.list_backups()
        self.assertEqual(len(records), 2)

    def test_list_backups_sorted_oldest_first(self):
        self.mgr.create_backup()
        time.sleep(0.01)
        self.mgr.create_backup()
        records = self.mgr.list_backups()
        self.assertLessEqual(records[0].created_at, records[1].created_at)

    def test_restore_success(self):
        record = self.mgr.create_backup()
        restore_path = os.path.join(self.tmpdir, "restored.db")
        result = self.mgr.restore(record.backup_id, target_path=restore_path)
        self.assertTrue(result.success)
        self.assertTrue(os.path.exists(restore_path))

    def test_restore_data_intact(self):
        record = self.mgr.create_backup()
        restore_path = os.path.join(self.tmpdir, "restored2.db")
        self.mgr.restore(record.backup_id, target_path=restore_path)
        conn = sqlite3.connect(restore_path)
        row = conn.execute("SELECT amount FROM orders WHERE id=1").fetchone()
        conn.close()
        self.assertAlmostEqual(row[0], 0.5)

    def test_restore_latest(self):
        self.mgr.create_backup()
        time.sleep(0.01)
        self.mgr.create_backup()
        restore_path = os.path.join(self.tmpdir, "restored_latest.db")
        result = self.mgr.restore_latest(target_path=restore_path)
        self.assertTrue(result.success)

    def test_restore_nonexistent_returns_failure(self):
        result = self.mgr.restore("no_such_backup")
        self.assertFalse(result.success)

    def test_prune_keeps_max_backups(self):
        mgr = DatabaseBackupManager(self.db_path, self.backup_dir, max_backups=3)
        for _ in range(5):
            mgr.create_backup()
        self.assertLessEqual(len(mgr.list_backups()), 3)

    def test_db_integrity_check(self):
        self.assertTrue(self.mgr.check_db_integrity())

    def test_db_integrity_check_missing_file(self):
        self.assertFalse(self.mgr.check_db_integrity("/nonexistent/path.db"))

    def test_get_status(self):
        self.mgr.create_backup()
        status = self.mgr.get_status()
        self.assertEqual(status["total_backups"], 1)
        self.assertIsNotNone(status["latest_backup"])

    def test_scheduler_start_stop(self):
        self.mgr.start_scheduler()
        self.assertTrue(self.mgr._scheduler_thread.is_alive())
        self.mgr.stop_scheduler()
        self.assertFalse(self.mgr._scheduler_thread.is_alive())

    def test_backup_manifest_persists(self):
        self.mgr.create_backup()
        # Re-create manager to re-read manifest from disk
        mgr2 = DatabaseBackupManager(self.db_path, self.backup_dir)
        self.assertEqual(len(mgr2.list_backups()), 1)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# DataIntegrityValidator tests
# ---------------------------------------------------------------------------
class TestDataIntegrityValidator(unittest.TestCase):
    def test_nan_detection(self):
        self.assertTrue(DataIntegrityValidator.has_nan_or_inf(float("nan")))
        self.assertTrue(DataIntegrityValidator.has_nan_or_inf(float("inf")))
        self.assertTrue(DataIntegrityValidator.has_nan_or_inf(float("-inf")))
        self.assertFalse(DataIntegrityValidator.has_nan_or_inf(3.14))
        self.assertFalse(DataIntegrityValidator.has_nan_or_inf("string"))

    def test_ohlcv_clean_candle(self):
        candle = {"open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000}
        violations = DataIntegrityValidator.check_ohlcv_consistency(candle)
        self.assertEqual(violations, [])

    def test_ohlcv_high_less_than_low(self):
        candle = {"open": 100, "high": 80, "low": 90, "close": 85}
        violations = DataIntegrityValidator.check_ohlcv_consistency(candle)
        self.assertTrue(any("high" in v and "low" in v for v in violations))

    def test_ohlcv_close_above_high(self):
        candle = {"open": 100, "high": 110, "low": 90, "close": 200}
        violations = DataIntegrityValidator.check_ohlcv_consistency(candle)
        self.assertTrue(any("close" in v for v in violations))

    def test_ohlcv_negative_volume(self):
        candle = {"open": 100, "high": 110, "low": 90, "close": 105, "volume": -50}
        violations = DataIntegrityValidator.check_ohlcv_consistency(candle)
        self.assertTrue(any("volume" in v for v in violations))

    def test_ohlcv_nan_field(self):
        candle = {"open": float("nan"), "high": 110, "low": 90, "close": 105}
        violations = DataIntegrityValidator.check_ohlcv_consistency(candle)
        self.assertTrue(any("NaN" in v for v in violations))

    def test_detect_price_spikes(self):
        prices = [100.0, 101.0, 99.0, 100.5, 10000.0, 100.2]  # index 4 is spike
        spikes = DataIntegrityValidator.detect_price_spikes(prices, z_threshold=2.0)
        spike_indices = [i for i, _ in spikes]
        self.assertIn(4, spike_indices)

    def test_detect_no_spikes_stable_series(self):
        prices = [100.0 + i * 0.1 for i in range(20)]
        spikes = DataIntegrityValidator.detect_price_spikes(prices, z_threshold=2.0)
        self.assertEqual(spikes, [])

    def test_detect_price_spikes_too_short(self):
        self.assertEqual(DataIntegrityValidator.detect_price_spikes([100.0, 200.0]), [])

    def test_validate_numeric_fields_clean(self):
        data = {"price": 100.5, "volume": 1000.0}
        violations = DataIntegrityValidator.validate_numeric_fields(
            data, ["price", "volume"]
        )
        self.assertEqual(violations, [])

    def test_validate_numeric_fields_missing(self):
        data = {"price": 100.5}
        violations = DataIntegrityValidator.validate_numeric_fields(
            data, ["price", "volume"]
        )
        self.assertTrue(any("volume" in v for v in violations))

    def test_validate_numeric_fields_nan(self):
        data = {"price": float("nan")}
        violations = DataIntegrityValidator.validate_numeric_fields(data, ["price"])
        self.assertTrue(any("NaN" in v for v in violations))

    def test_checksum_stable(self):
        data = {"price": 100, "symbol": "BTC-USD"}
        c1 = DataIntegrityValidator.compute_checksum(data)
        c2 = DataIntegrityValidator.compute_checksum(data)
        self.assertEqual(c1, c2)

    def test_checksum_verify(self):
        data = {"price": 100}
        cs = DataIntegrityValidator.compute_checksum(data)
        self.assertTrue(DataIntegrityValidator.verify_checksum(data, cs))
        self.assertFalse(DataIntegrityValidator.verify_checksum({"price": 200}, cs))

    def test_batch_integrity_all_clean(self):
        records = [{"price": 100.0, "volume": 10.0} for _ in range(5)]
        result = DataIntegrityValidator.check_batch_integrity(
            records, ["price", "volume"]
        )
        self.assertTrue(result["integrity_ok"])
        self.assertEqual(result["corrupt"], 0)

    def test_batch_integrity_detects_nan(self):
        records = [
            {"price": 100.0, "volume": 10.0},
            {"price": float("nan"), "volume": 10.0},
        ]
        result = DataIntegrityValidator.check_batch_integrity(
            records, ["price", "volume"]
        )
        self.assertFalse(result["integrity_ok"])
        self.assertIn(1, result["corrupt_indices"])

    def test_batch_integrity_detects_missing_field(self):
        records = [{"price": 100.0}, {"price": 200.0}]
        result = DataIntegrityValidator.check_batch_integrity(
            records, ["price", "volume"]
        )
        self.assertFalse(result["integrity_ok"])


if __name__ == "__main__":
    unittest.main()
