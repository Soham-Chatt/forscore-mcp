"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from .errors import ForScoreError, LibraryNotFoundError

# Core Data stores timestamps as seconds since 2001-01-01 UTC.
_CORE_DATA_EPOCH = 978307200


def core_data_now() -> float:
    return time.time() - _CORE_DATA_EPOCH


def connect(path: Path, *, write: bool = False) -> sqlite3.Connection:
    """Open the library. Read-only unless ``write`` is set; autocommit, explicit transactions."""
    if not path.exists():
        raise LibraryNotFoundError(
            f"No forScore library at {path}. Is forScore installed on this Mac? "
            "Set FORSCORE_LIBRARY to use another location."
        )
    uri = f"{path.resolve().as_uri()}?mode={'rw' if write else 'ro'}"
    try:
        conn = sqlite3.connect(uri, uri=True, isolation_level=None)
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
    except sqlite3.OperationalError as exc:
        raise LibraryNotFoundError(
            f"Cannot open {path} ({exc}). On macOS, give your terminal or AI app "
            "Full Disk Access in System Settings > Privacy & Security."
        ) from exc
    return conn


def snapshot(conn: sqlite3.Connection) -> sqlite3.Connection:
    """In-memory copy of a database, for dry runs that must never touch the original."""
    copy = sqlite3.connect(":memory:", isolation_level=None)
    conn.backup(copy)
    return copy


def require_integrity(conn: sqlite3.Connection) -> None:
    result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise ForScoreError(f"Library integrity check failed: {result}")


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
