"""Guards and backups around writes to the live library."""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import syncfiles
from .errors import AppRunningError, NotFoundError

BACKUP_NAME = "library.4sl"
SYNC_BACKUP = "Sync"


def forscore_running() -> bool:
    """True if a forScore process is running. Always False where pgrep is unavailable."""
    if shutil.which("pgrep") is None:
        return False
    return subprocess.run(["pgrep", "-x", "forScore"], capture_output=True).returncode == 0


def require_quit() -> None:
    if forscore_running():
        raise AppRunningError(
            "forScore is running on this Mac. Quit it (Cmd-Q) before writing, otherwise it may "
            "overwrite the changes or fail to sync them. Your iPad can stay open."
        )


@dataclass(frozen=True)
class Backup:
    id: str
    path: Path

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "path": str(self.path)}


def create_backup(
    conn: sqlite3.Connection, directory: Path, sync_dir: Path | None = None
) -> Backup:
    """Snapshot the database (via SQLite's backup API, so WAL pages are included) and,
    if given, the per-score sync files."""
    backup_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = directory / backup_id / BACKUP_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as dest:
        conn.backup(dest)
    dest.close()
    if sync_dir is not None and sync_dir.is_dir():
        syncfiles.copy_dir(sync_dir, target.parent / SYNC_BACKUP)
    return Backup(backup_id, target)


def list_backups(directory: Path) -> list[Backup]:
    if not directory.exists():
        return []
    found = (Backup(p.parent.name, p) for p in directory.glob(f"*/{BACKUP_NAME}"))
    return sorted(found, key=lambda b: b.id, reverse=True)


def find_backup(directory: Path, backup_id: str) -> Backup:
    for backup in list_backups(directory):
        if backup.id == backup_id:
            return backup
    raise NotFoundError(f"No backup {backup_id!r} in {directory}.")


def restore_backup(backup: Backup, conn: sqlite3.Connection, sync_dir: Path | None = None) -> None:
    """Overwrite the open library in place (through SQLite, so the WAL stays consistent),
    and the sync files if the backup has them."""
    with sqlite3.connect(f"{backup.path.resolve().as_uri()}?mode=ro", uri=True) as source:
        source.backup(conn)
    source.close()
    restore_sync_files(backup, sync_dir)


def restore_sync_files(backup: Backup, sync_dir: Path | None) -> None:
    saved = backup.path.parent / SYNC_BACKUP
    if sync_dir is not None and saved.is_dir():
        syncfiles.copy_dir(saved, sync_dir)
