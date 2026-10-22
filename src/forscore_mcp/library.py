"""High-level API used by the CLI and MCP server. All safety policy lives here."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import changeset as cs
from . import paths, safety, syncfiles
from .audit import AuditReport
from .audit import run as run_audit
from .db import connect, require_integrity, snapshot, transaction
from .models import FIELDS, Item, ItemKind, MetaKind, MetaValue, Setlist
from .repository import Store


@dataclass(frozen=True)
class Filters:
    """Item filters; all given criteria must match. Value filters are exact, case-insensitive."""

    query: str | None = None  # substring of title, parent, reference, composers, genres, tags
    kind: ItemKind | None = None
    composer: str | None = None
    genre: str | None = None
    tag: str | None = None
    label: str | None = None
    library: str | None = None
    missing: str | None = None  # a field name: only items where it is empty

    def matches(self, item: Item) -> bool:
        if self.kind and item.kind is not self.kind:
            return False
        if self.query and self.query.casefold() not in _haystack(item):
            return False
        for wanted, values in (
            (self.composer, item.composers), (self.genre, item.genres), (self.tag, item.tags),
            (self.label, item.labels), (self.library, item.libraries),
        ):  # fmt: skip
            if wanted and wanted.casefold() not in {v.casefold() for v in values}:
                return False
        return not self.missing or item.get(self.missing) in (None, [], "")


@dataclass(frozen=True)
class Page:
    total: int
    offset: int
    items: list[Item]


class Library:
    def __init__(self, path: Path | None = None, backup_dir: Path | None = None) -> None:
        self.path = path or paths.library_path()
        self.backup_dir = backup_dir or paths.backup_dir()
        self.sync_dir = syncfiles.sync_dir(self.path)
        self.documents = paths.documents_dir(self.path)

    @contextmanager
    def _store(self, *, write: bool = False) -> Generator[Store]:
        with closing(connect(self.path, write=write)) as conn:
            yield Store(conn)

    # ---- reads -------------------------------------------------------------------------

    def items(self, filters: Filters | None = None) -> list[Item]:
        filters = filters or Filters()
        if filters.missing and filters.missing not in FIELDS:
            raise ValueError(f"Unknown field {filters.missing!r}; use one of {list(FIELDS)}.")
        with self._store() as store:
            return [item for item in store.items() if filters.matches(item)]

    def page(self, filters: Filters | None = None, *, offset: int = 0, limit: int = 50) -> Page:
        items = self.items(filters)
        return Page(len(items), offset, items[offset : offset + max(limit, 0)])

    def item(self, match: str) -> Item:
        with self._store() as store:
            return store.item(store.find(match))

    def values(self, kind: MetaKind) -> list[MetaValue]:
        with self._store() as store:
            return store.values(kind)

    def setlists(self) -> list[Setlist]:
        with self._store() as store:
            return store.setlists()

    def audit(self) -> AuditReport:
        with self._store() as store:
            items, composers = store.items(), store.values(MetaKind.COMPOSERS)
        return run_audit(items, composers, self.documents)

    def sync_drift(self) -> list[syncfiles.Drift]:
        """Differences between the library and the sync files other devices receive."""
        return syncfiles.drift(self.sync_dir, self.items())

    # ---- writes ------------------------------------------------------------------------

    def preview(self, data: object) -> cs.Report:
        """Run a changeset on an in-memory copy. Safe while forScore is open."""
        changeset = cs.parse(data)
        with closing(connect(self.path)) as conn, closing(snapshot(conn)) as copy:
            return cs.run(Store(copy), changeset, dry_run=True)

    def apply(self, data: object) -> cs.Report:
        """Back up, then apply a changeset to the database and the sync files.

        The database changes run in one transaction; if writing any sync file fails, the
        transaction rolls back and the sync files are restored from the backup.
        """
        changeset = cs.parse(data)
        self.preview(data)  # fail on a copy (bad match, bad key...) before backing up/writing
        with self._writable() as conn:
            backup = safety.create_backup(conn, self.backup_dir, self.sync_dir)
            try:
                with transaction(conn):
                    report = cs.run(Store(conn), changeset, dry_run=False)
                    require_integrity(conn)
                    report.sync_files_updated = sum(
                        syncfiles.update(self.sync_dir, score) for score in report.updated
                    )
            except BaseException:
                safety.restore_sync_files(backup, self.sync_dir)
                raise
        report.backup = backup.id
        return report

    def backup(self) -> safety.Backup:
        with closing(connect(self.path)) as conn:
            return safety.create_backup(conn, self.backup_dir, self.sync_dir)

    def backups(self) -> list[safety.Backup]:
        return safety.list_backups(self.backup_dir)

    def restore(self, backup_id: str) -> safety.Backup:
        """Replace the library with a backup, after backing up the current state."""
        source = safety.find_backup(self.backup_dir, backup_id)
        with self._writable() as conn:
            current = safety.create_backup(conn, self.backup_dir, self.sync_dir)
            safety.restore_backup(source, conn, self.sync_dir)
            require_integrity(conn)
        return current

    @contextmanager
    def _writable(self) -> Generator[sqlite3.Connection]:
        safety.require_quit()
        with closing(connect(self.path, write=True)) as conn:
            Store(conn)  # schema check
            require_integrity(conn)
            yield conn


def _haystack(item: Item) -> str:
    parts = [item.name, item.reference or "", *item.composers, *item.genres, *item.tags]
    return " ".join(parts).casefold()
