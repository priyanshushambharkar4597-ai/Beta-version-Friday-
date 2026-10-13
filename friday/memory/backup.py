"""Vault Snapshot Backup & Restore Manager for Friday."""

from __future__ import annotations

import datetime
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from friday.tools.base import BaseTool, PermissionTier


class VaultBackupManager:
    """Manages timestamped zip archives and restoration of the Obsidian Vault."""

    def __init__(
        self,
        vault_dir: str = "vault",
        backup_dir: str = "backups",
        max_backups: int = 10,
    ) -> None:
        self.vault_dir = Path(vault_dir).resolve()
        self.backup_dir = Path(backup_dir).resolve()
        self.max_backups = max_backups
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, reason: str = "manual") -> Dict[str, Any]:
        """Compress vault into timestamped .zip archive and prune old backups."""
        if not self.vault_dir.exists():
            raise FileNotFoundError(f"Vault directory does not exist: {self.vault_dir}")

        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_filename = f"vault_backup_{timestamp_str}.zip"
        backup_path = self.backup_dir / backup_filename

        notes_count = 0
        total_files = 0

        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(self.vault_dir):
                for file in files:
                    full_path = Path(root) / file
                    arcname = full_path.relative_to(self.vault_dir)
                    zf.write(full_path, arcname)
                    total_files += 1
                    if file.endswith(".md"):
                        notes_count += 1

        size_bytes = backup_path.stat().st_size
        self._prune_old_backups()

        return {
            "status": "success",
            "backup_name": backup_filename,
            "backup_path": str(backup_path),
            "size_bytes": size_bytes,
            "notes_count": notes_count,
            "total_files": total_files,
            "timestamp": timestamp_str,
            "reason": reason,
        }

    def list_backups(self) -> List[Dict[str, Any]]:
        """List available backups sorted by creation time descending."""
        if not self.backup_dir.exists():
            return []

        backups: List[Dict[str, Any]] = []
        for item in self.backup_dir.glob("vault_backup_*.zip"):
            stat = item.stat()
            notes_count = 0
            file_count = 0
            try:
                with zipfile.ZipFile(item, "r") as zf:
                    names = zf.namelist()
                    file_count = len(names)
                    notes_count = sum(1 for n in names if n.endswith(".md"))
            except Exception:
                pass

            dt_created = datetime.datetime.fromtimestamp(stat.st_mtime)
            backups.append({
                "backup_name": item.name,
                "backup_path": str(item),
                "size_bytes": stat.st_size,
                "total_files": file_count,
                "notes_count": notes_count,
                "created_at": dt_created.isoformat(),
                "mtime": stat.st_mtime,
            })

        backups.sort(key=lambda x: x["mtime"], reverse=True)
        return backups

    def restore_backup(self, backup_name: str = "latest") -> Dict[str, Any]:
        """Restore vault contents from a specified backup or the latest one."""
        if not self.backup_dir.exists():
            raise FileNotFoundError("Backup directory does not exist.")

        target_zip: Optional[Path] = None
        if backup_name.lower() in ("latest", "last"):
            backups = self.list_backups()
            if not backups:
                raise FileNotFoundError("No vault backups available to restore.")
            target_zip = Path(backups[0]["backup_path"])
        else:
            cand = self.backup_dir / backup_name
            if not cand.exists() and not backup_name.endswith(".zip"):
                cand = self.backup_dir / f"{backup_name}.zip"
            if not cand.exists():
                direct_cand = Path(backup_name)
                if direct_cand.exists():
                    cand = direct_cand
                else:
                    raise FileNotFoundError(f"Backup file not found: {backup_name}")
            target_zip = cand

        self.vault_dir.mkdir(parents=True, exist_ok=True)

        restored_files = 0
        with zipfile.ZipFile(target_zip, "r") as zf:
            for member in zf.infolist():
                zf.extract(member, self.vault_dir)
                restored_files += 1

        return {
            "status": "success",
            "restored_from": target_zip.name,
            "backup_path": str(target_zip),
            "restored_files_count": restored_files,
            "vault_dir": str(self.vault_dir),
        }

    def _prune_old_backups(self) -> None:
        """Keep only the latest max_backups archives."""
        backups = self.list_backups()
        if len(backups) > self.max_backups:
            for old in backups[self.max_backups :]:
                p = Path(old["backup_path"])
                if p.exists():
                    p.unlink(missing_ok=True)


class BackupVaultTool(BaseTool):
    """Tool to create a timestamped backup of the Obsidian vault."""

    name = "backup_vault"
    description = (
        "Create a timestamped compressed .zip backup archive of the Obsidian vault "
        "into backups/ directory. Automatically retains the 10 most recent backups."
    )
    tier = PermissionTier.REVERSIBLE

    def __init__(self, manager: Optional[VaultBackupManager] = None) -> None:
        self.manager = manager or VaultBackupManager()

    def execute(self, reason: str = "manual", **kwargs: Any) -> Dict[str, Any]:
        return self.manager.create_backup(reason=reason)


class ListVaultBackupsTool(BaseTool):
    """Tool to list available vault backup archives."""

    name = "list_vault_backups"
    description = (
        "List all available Obsidian vault backups with timestamp, file size, "
        "and note counts."
    )
    tier = PermissionTier.READ

    def __init__(self, manager: Optional[VaultBackupManager] = None) -> None:
        self.manager = manager or VaultBackupManager()

    def execute(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return self.manager.list_backups()


class RestoreVaultBackupTool(BaseTool):
    """Tool to restore Obsidian vault from a backup archive."""

    name = "restore_vault_backup"
    description = (
        "Restore the Obsidian vault from a specified backup archive (or 'latest'). "
        "Overwrites existing vault files with the archived state."
    )
    tier = PermissionTier.IRREVERSIBLE

    def __init__(self, manager: Optional[VaultBackupManager] = None) -> None:
        self.manager = manager or VaultBackupManager()

    def execute(self, backup_name: str = "latest", **kwargs: Any) -> Dict[str, Any]:
        return self.manager.restore_backup(backup_name=backup_name)
