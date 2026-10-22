"""Guards and backups around writes to the live library."""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .errors import AppRunningError, NotFoundError

BACKUP_NAME = "library.4sl"


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


def create_backup(conn: sqlite3.Connection, directory: Path) -> Backup:
    """Consistent snapshot (including uncommitted WAL pages) via SQLite's backup API."""
    backup_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = directory / backup_id / BACKUP_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as dest:
        conn.backup(dest)
    dest.close()
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


def restore_backup(backup: Backup, conn: sqlite3.Connection) -> None:
    """Overwrite the open library in place; goes through SQLite so the WAL stays consistent."""
    with sqlite3.connect(f"{backup.path.resolve().as_uri()}?mode=ro", uri=True) as source:
        source.backup(conn)
    source.close()
