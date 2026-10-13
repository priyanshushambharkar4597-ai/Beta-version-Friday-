"""Unit tests for Friday Vault Snapshot Backup & Restore Manager."""

import tempfile
from pathlib import Path
import pytest

from friday.memory.backup import (
    VaultBackupManager,
    BackupVaultTool,
    ListVaultBackupsTool,
    RestoreVaultBackupTool,
)
from friday.tools.base import PermissionTier


def test_vault_backup_creation_and_listing():
    """Verify VaultBackupManager creates timestamped .zip and lists metadata."""
    with tempfile.TemporaryDirectory() as tmp_vault, tempfile.TemporaryDirectory() as tmp_backup:
        v_path = Path(tmp_vault)
        (v_path / "Note1.md").write_text("# Note 1\nSome contents.", encoding="utf-8")
        (v_path / "Note2.md").write_text("# Note 2\n[[Note1]]", encoding="utf-8")
        (v_path / "attachments").mkdir()
        (v_path / "attachments" / "plot.png").write_bytes(b"FAKE_PNG_BYTES")

        mgr = VaultBackupManager(vault_dir=tmp_vault, backup_dir=tmp_backup, max_backups=5)
        res = mgr.create_backup(reason="unit_test")

        assert res["status"] == "success"
        assert res["notes_count"] == 2
        assert res["total_files"] == 3
        assert Path(res["backup_path"]).exists()

        backups = mgr.list_backups()
        assert len(backups) == 1
        assert backups[0]["notes_count"] == 2
        assert backups[0]["total_files"] == 3


def test_vault_restore():
    """Verify VaultBackupManager restores corrupted or deleted notes from latest backup."""
    with tempfile.TemporaryDirectory() as tmp_vault, tempfile.TemporaryDirectory() as tmp_backup:
        v_path = Path(tmp_vault)
        (v_path / "Design.md").write_text("# Circuit Design\nOpAmp inverting amplifier.", encoding="utf-8")

        mgr = VaultBackupManager(vault_dir=tmp_vault, backup_dir=tmp_backup)
        mgr.create_backup(reason="pre_corruption")

        # Corrupt and delete
        (v_path / "Design.md").unlink()
        assert not (v_path / "Design.md").exists()

        # Restore from latest
        restored = mgr.restore_backup(backup_name="latest")
        assert restored["status"] == "success"
        assert (v_path / "Design.md").exists()
        assert "Circuit Design" in (v_path / "Design.md").read_text(encoding="utf-8")


def test_backup_pruning_policy():
    """Verify VaultBackupManager maintains at most max_backups archives."""
    with tempfile.TemporaryDirectory() as tmp_vault, tempfile.TemporaryDirectory() as tmp_backup:
        v_path = Path(tmp_vault)
        (v_path / "Note.md").write_text("# Note", encoding="utf-8")

        mgr = VaultBackupManager(vault_dir=tmp_vault, backup_dir=tmp_backup, max_backups=3)
        for i in range(5):
            mgr.create_backup(reason=f"backup_{i}")

        backups = mgr.list_backups()
        assert len(backups) == 3


def test_backup_tools_metadata_and_execution():
    """Verify BaseTool wrappers for backup operations adhere to safety tiers."""
    with tempfile.TemporaryDirectory() as tmp_vault, tempfile.TemporaryDirectory() as tmp_backup:
        v_path = Path(tmp_vault)
        (v_path / "Note.md").write_text("# Note", encoding="utf-8")

        mgr = VaultBackupManager(vault_dir=tmp_vault, backup_dir=tmp_backup)

        b_tool = BackupVaultTool(mgr)
        l_tool = ListVaultBackupsTool(mgr)
        r_tool = RestoreVaultBackupTool(mgr)

        assert b_tool.tier == PermissionTier.REVERSIBLE
        assert l_tool.tier == PermissionTier.READ
        assert r_tool.tier == PermissionTier.IRREVERSIBLE

        # Run tools
        b_res = b_tool.execute(reason="tool_test")
        assert b_res["status"] == "success"

        l_res = l_tool.execute()
        assert len(l_res) == 1

        (v_path / "Note.md").unlink()
        r_res = r_tool.execute(backup_name="latest")
        assert r_res["status"] == "success"
        assert (v_path / "Note.md").exists()
