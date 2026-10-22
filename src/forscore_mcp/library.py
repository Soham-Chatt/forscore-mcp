"""High-level API used by the CLI and MCP server. All safety policy lives here."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path

from . import changeset as cs
from . import paths, safety
from .db import connect, require_integrity, snapshot, transaction
from .models import MetaKind, MetaValue, Score
from .repository import Store


class Library:
    def __init__(self, path: Path | None = None, backup_dir: Path | None = None) -> None:
        self.path = path or paths.library_path()
        self.backup_dir = backup_dir or paths.backup_dir()

    @contextmanager
    def _store(self, *, write: bool = False) -> Generator[Store]:
        with closing(connect(self.path, write=write)) as conn:
            yield Store(conn)

    # ---- reads -------------------------------------------------------------------------

    def scores(self, query: str | None = None) -> list[Score]:
        with self._store() as store:
            scores = store.scores()
        if not query:
            return scores
        needle = query.casefold()
        return [s for s in scores if needle in _haystack(s)]

    def score(self, match: str) -> Score:
        with self._store() as store:
            return store.score(store.find(match))

    def values(self, kind: MetaKind) -> list[MetaValue]:
        with self._store() as store:
            return store.values(kind)

    # ---- writes ------------------------------------------------------------------------

    def preview(self, data: object) -> cs.Report:
        """Run a changeset on an in-memory copy. Safe while forScore is open."""
        changeset = cs.parse(data)
        with closing(connect(self.path)) as conn, closing(snapshot(conn)) as copy:
            return cs.run(Store(copy), changeset, dry_run=True)

    def apply(self, data: object) -> cs.Report:
        """Back up, then apply a changeset to the live library in one transaction."""
        changeset = cs.parse(data)
        self.preview(data)  # fail on a copy (bad match, bad key...) before backing up/writing
        with self._writable() as conn:
            backup = safety.create_backup(conn, self.backup_dir)
            with transaction(conn):
                report = cs.run(Store(conn), changeset, dry_run=False)
                require_integrity(conn)
        report.backup = backup.id
        return report

    def backup(self) -> safety.Backup:
        with closing(connect(self.path)) as conn:
            return safety.create_backup(conn, self.backup_dir)

    def backups(self) -> list[safety.Backup]:
        return safety.list_backups(self.backup_dir)

    def restore(self, backup_id: str) -> safety.Backup:
        """Replace the library with a backup, after backing up the current state."""
        source = safety.find_backup(self.backup_dir, backup_id)
        with self._writable() as conn:
            current = safety.create_backup(conn, self.backup_dir)
            safety.restore_backup(source, conn)
            require_integrity(conn)
        return current

    @contextmanager
    def _writable(self) -> Generator[sqlite3.Connection]:
        safety.require_quit()
        with closing(connect(self.path, write=True)) as conn:
            Store(conn)  # schema check
            require_integrity(conn)
            yield conn


def _haystack(score: Score) -> str:
    parts = [score.title, score.reference or "", *score.composers, *score.genres, *score.tags]
    return " ".join(parts).casefold()
