"""
PowerTraderAI+ Automated Database Backup & Restore System
Handles scheduled SQLite backups, integrity verification, and
point-in-time recovery with configurable retention policy.
"""

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class BackupRecord:
    """Metadata for a single backup file."""

    backup_id: str
    source_db: str
    backup_path: str
    created_at: float
    file_size_bytes: int
    sha256_checksum: str
    integrity_check_passed: bool
    notes: str = ""

    def created_at_iso(self) -> str:
        return datetime.fromtimestamp(self.created_at).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at_iso"] = self.created_at_iso()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BackupRecord":
        d.pop("created_at_iso", None)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RestoreResult:
    """Result of a restore operation."""

    success: bool
    backup_id: str
    restored_from: str
    restored_to: str
    message: str
    timestamp: float


# ---------------------------------------------------------------------------
# DatabaseBackupManager
# ---------------------------------------------------------------------------
class DatabaseBackupManager:
    """
    Manages automated backup and restore for SQLite databases.

    Features:
    - SHA-256 checksums for backup integrity verification
    - SQLite PRAGMA integrity_check before backup
    - WAL checkpoint to ensure all data is flushed
    - Configurable retention (keep last N backups)
    - Point-in-time recovery (restore any stored backup)
    - Background scheduler thread for automated backups

    Args:
        db_path: Path to the SQLite database file
        backup_dir: Directory to store backup files (auto-created)
        max_backups: Maximum number of backups to retain
        backup_interval_hours: Hours between automated backups
    """

    MANIFEST_FILE = "backup_manifest.json"

    def __init__(
        self,
        db_path: str,
        backup_dir: Optional[str] = None,
        max_backups: int = 30,
        backup_interval_hours: float = 24.0,
    ):
        self.db_path = os.path.abspath(db_path)
        self.backup_dir = backup_dir or os.path.join(
            os.path.dirname(self.db_path), "backups"
        )
        self.max_backups = max_backups
        self.backup_interval = backup_interval_hours * 3600
        self._manifest_path = os.path.join(self.backup_dir, self.MANIFEST_FILE)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None
        os.makedirs(self.backup_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Checksum
    # ------------------------------------------------------------------
    def _sha256(self, path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    # ------------------------------------------------------------------
    # Integrity check
    # ------------------------------------------------------------------
    def check_db_integrity(self, db_path: Optional[str] = None) -> bool:
        """Run SQLite integrity_check PRAGMA. Returns True if OK."""
        path = db_path or self.db_path
        if not os.path.exists(path):
            logger.warning("DB integrity check skipped — file not found: %s", path)
            return False
        try:
            conn = sqlite3.connect(path)
            cursor = conn.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            conn.close()
            ok = result and result[0] == "ok"
            if not ok:
                logger.error("DB integrity check FAILED for %s: %s", path, result)
            return ok
        except sqlite3.Error as exc:
            logger.error("DB integrity check error for %s: %s", path, exc)
            return False

    # ------------------------------------------------------------------
    # Backup
    # ------------------------------------------------------------------
    def create_backup(self, notes: str = "") -> Optional[BackupRecord]:
        """
        Create a verified backup of the database.

        Steps:
        1. WAL checkpoint (flush WAL to main DB)
        2. Integrity check source DB
        3. Copy to backup file
        4. Verify backup checksum
        5. Integrity check backup
        6. Register in manifest
        7. Prune old backups if over limit

        Returns:
            BackupRecord on success, None on failure.
        """
        with self._lock:
            if not os.path.exists(self.db_path):
                logger.error("Source DB not found: %s", self.db_path)
                return None

            # Step 1: WAL checkpoint
            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
            except sqlite3.Error as exc:
                logger.warning("WAL checkpoint failed (non-fatal): %s", exc)

            # Step 2: Integrity check
            if not self.check_db_integrity():
                logger.error("Source DB integrity check failed — aborting backup")
                return None

            # Step 3: Copy
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_id = f"backup_{ts}"
            backup_path = os.path.join(self.backup_dir, f"{backup_id}.db")

            try:
                shutil.copy2(self.db_path, backup_path)
            except OSError as exc:
                logger.error("Failed to copy DB to backup: %s", exc)
                return None

            # Step 4 & 5: Checksum + integrity on backup
            checksum = self._sha256(backup_path)
            integrity_ok = self.check_db_integrity(backup_path)
            file_size = os.path.getsize(backup_path)

            record = BackupRecord(
                backup_id=backup_id,
                source_db=self.db_path,
                backup_path=backup_path,
                created_at=time.time(),
                file_size_bytes=file_size,
                sha256_checksum=checksum,
                integrity_check_passed=integrity_ok,
                notes=notes,
            )

            # Step 6: Register
            self._append_manifest(record)
            logger.info(
                "Backup created: %s (%d bytes, integrity=%s)",
                backup_id,
                file_size,
                integrity_ok,
            )

            # Step 7: Prune
            self._prune_old_backups()

            return record

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------
    def verify_backup(self, backup_id: str) -> bool:
        """Verify a backup's SHA-256 checksum and SQLite integrity."""
        record = self._get_record(backup_id)
        if not record:
            logger.error("Backup record not found: %s", backup_id)
            return False
        if not os.path.exists(record.backup_path):
            logger.error("Backup file missing: %s", record.backup_path)
            return False

        current_checksum = self._sha256(record.backup_path)
        if current_checksum != record.sha256_checksum:
            logger.error(
                "Backup checksum MISMATCH for %s: expected %s, got %s",
                backup_id,
                record.sha256_checksum,
                current_checksum,
            )
            return False

        integrity = self.check_db_integrity(record.backup_path)
        logger.info(
            "Backup %s verified: checksum OK, integrity=%s", backup_id, integrity
        )
        return integrity

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------
    def restore(
        self, backup_id: str, target_path: Optional[str] = None
    ) -> RestoreResult:
        """
        Restore a backup to target_path (default: overwrites source DB).

        Safety: atomic swap — copy to temp file, verify, then rename.
        """
        with self._lock:
            record = self._get_record(backup_id)
            if not record:
                return RestoreResult(
                    success=False,
                    backup_id=backup_id,
                    restored_from="",
                    restored_to="",
                    message=f"Backup record not found: {backup_id}",
                    timestamp=time.time(),
                )

            # Verify before restore
            if not self.verify_backup(backup_id):
                return RestoreResult(
                    success=False,
                    backup_id=backup_id,
                    restored_from=record.backup_path,
                    restored_to="",
                    message="Backup verification failed — restore aborted",
                    timestamp=time.time(),
                )

            target = target_path or self.db_path
            tmp_path = target + ".restore_tmp"

            try:
                shutil.copy2(record.backup_path, tmp_path)
                # Atomic replace
                os.replace(tmp_path, target)
                logger.info("Restored %s → %s", backup_id, target)
                return RestoreResult(
                    success=True,
                    backup_id=backup_id,
                    restored_from=record.backup_path,
                    restored_to=target,
                    message="Restore successful",
                    timestamp=time.time(),
                )
            except OSError as exc:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                logger.error("Restore failed: %s", exc)
                return RestoreResult(
                    success=False,
                    backup_id=backup_id,
                    restored_from=record.backup_path,
                    restored_to=target,
                    message=f"Restore failed: {exc}",
                    timestamp=time.time(),
                )

    def restore_latest(self, target_path: Optional[str] = None) -> RestoreResult:
        """Restore the most recent backup."""
        records = self.list_backups()
        if not records:
            return RestoreResult(
                success=False,
                backup_id="",
                restored_from="",
                restored_to="",
                message="No backups available",
                timestamp=time.time(),
            )
        return self.restore(records[-1].backup_id, target_path)

    # ------------------------------------------------------------------
    # List / manifest
    # ------------------------------------------------------------------
    def list_backups(self) -> List[BackupRecord]:
        """Return all backup records, sorted oldest-first."""
        manifest = self._load_manifest()
        return sorted(manifest, key=lambda r: r.created_at)

    def _load_manifest(self) -> List[BackupRecord]:
        if not os.path.exists(self._manifest_path):
            return []
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                entries = json.load(f)
            return [BackupRecord.from_dict(e) for e in entries]
        except (OSError, json.JSONDecodeError, TypeError):
            return []

    def _save_manifest(self, records: List[BackupRecord]) -> None:
        with open(self._manifest_path, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in records], f, indent=2)

    def _append_manifest(self, record: BackupRecord) -> None:
        records = self._load_manifest()
        records.append(record)
        self._save_manifest(records)

    def _get_record(self, backup_id: str) -> Optional[BackupRecord]:
        return next(
            (r for r in self._load_manifest() if r.backup_id == backup_id), None
        )

    def _prune_old_backups(self) -> int:
        """Delete oldest backups when over max_backups limit. Returns count pruned."""
        records = self.list_backups()
        to_prune = records[: max(0, len(records) - self.max_backups)]
        for record in to_prune:
            try:
                os.remove(record.backup_path)
                logger.info("Pruned old backup: %s", record.backup_id)
            except OSError as exc:
                logger.warning("Could not remove old backup file: %s", exc)
        if to_prune:
            remaining = [r for r in records if r not in to_prune]
            self._save_manifest(remaining)
        return len(to_prune)

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------
    def start_scheduler(self) -> None:
        """Start automated backup scheduler as daemon thread."""
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(
            target=self._run_scheduler,
            name="DBBackupScheduler",
            daemon=True,
        )
        self._scheduler_thread.start()
        logger.info(
            "DB backup scheduler started (interval: %gh, max_backups: %d)",
            self.backup_interval / 3600,
            self.max_backups,
        )

    def stop_scheduler(self) -> None:
        self._stop_event.set()
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        logger.info("DB backup scheduler stopped")

    def _run_scheduler(self) -> None:
        while not self._stop_event.is_set():
            try:
                record = self.create_backup(notes="scheduled")
                if record:
                    logger.info("Scheduled backup complete: %s", record.backup_id)
                else:
                    logger.error("Scheduled backup FAILED")
            except Exception as exc:
                logger.error("Backup scheduler error: %s", exc)
            self._stop_event.wait(timeout=self.backup_interval)

    def get_status(self) -> Dict:
        """Return backup system status summary."""
        records = self.list_backups()
        return {
            "total_backups": len(records),
            "latest_backup": records[-1].to_dict() if records else None,
            "backup_dir": self.backup_dir,
            "max_backups": self.max_backups,
            "scheduler_running": bool(
                self._scheduler_thread and self._scheduler_thread.is_alive()
            ),
        }
