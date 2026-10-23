"""Guards and backups around writes to the live library."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import paths, syncfiles
from .errors import AppRunningError, DirectWritesDisabledError, NotFoundError

DIRECT_WRITES_ENV = "FORSCORE_DIRECT_WRITES"
DIRECT_WRITES_PHRASE = "i-understand-this-can-damage-my-library"
ENABLE_COMMAND = f"forscore-mcp direct-writes enable {DIRECT_WRITES_PHRASE}"
DIRECT_WRITES_RISK = (
    "Direct writes edit forScore's database and sync files themselves, which forScore does not "
    "support: values are not checked by forScore and can cause crashes, unexpected behaviour or "
    "data loss. The supported way is the CSV import (the default)."
)
DIRECT_WRITE_WARNING = (
    "Direct write: forScore's database and sync files were edited directly (unsupported by "
    "forScore). A backup was made first."
)
BACKUP_NAME = "library.4sl"
SYNC_BACKUP = "Sync"


def forscore_running() -> bool:
    """True if a forScore process is running. Always False where pgrep is unavailable."""
    if shutil.which("pgrep") is None:
        return False
    return subprocess.run(["pgrep", "-x", "forScore"], capture_output=True).returncode == 0


def direct_writes_enabled() -> bool:
    """On if enabled with `forscore-mcp direct-writes enable` or via the environment variable."""
    if os.environ.get(DIRECT_WRITES_ENV) == DIRECT_WRITES_PHRASE:
        return True
    return bool(_read_config().get("direct_writes"))


def set_direct_writes(enabled: bool) -> None:
    config = _read_config() | {"direct_writes": enabled}
    path = paths.config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n")


def require_direct_writes() -> None:
    if not direct_writes_enabled():
        raise DirectWritesDisabledError(
            f"Direct writes are off. {DIRECT_WRITES_RISK} To accept that risk, the user can run "
            f"`{ENABLE_COMMAND}` (and `forscore-mcp direct-writes disable` to turn it off)."
        )


def _read_config() -> dict[str, object]:
    try:
        data = json.loads(paths.config_file().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


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
