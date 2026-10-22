"""Read and write primitives on an open library connection.

Writes here are low-level and do no safety checks of their own; callers go through
`library.Library`, which adds guards, backups, transactions and sync-file updates.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable

from . import keys
from .db import core_data_now
from .errors import ChangesetError, NotFoundError
from .models import (
    MAX_DIFFICULTY,
    MAX_RATING,
    Item,
    ItemKind,
    MetaKind,
    MetaValue,
    Setlist,
    format_duration,
    parse_duration,
)
from .schema import (
    ITEM_TABLE,
    META_TABLE,
    SETLIST_ENTRY_TABLE,
    SETLIST_TABLE,
    Schema,
)
from .sorttitle import sort_title

_PATH_SEPARATOR = re.compile(r"\s*[›>]\s*")
_SCALE_MAX = {"rating": MAX_RATING, "difficulty": MAX_DIFFICULTY}


def _decode_key(code: object) -> str | None:
    if code in (None, "", 0):
        return None
    try:
        return keys.decode(int(str(code)))
    except ValueError:
        return f"unknown ({code})"


def _pages(start: int | None, end: int | None) -> str | None:
    if start is None:
        return None
    return str(start) if end in (None, start) else f"{start}-{end}"


class Store:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.schema = Schema.load(conn)

    # ---- reads -------------------------------------------------------------------------

    def item_pks(self) -> list[int]:
        """Scores in sort order, each followed by its bookmarks in page order."""
        s = self.schema
        rows = self.conn.execute(
            f"SELECT i.Z_PK FROM {ITEM_TABLE} i LEFT JOIN {ITEM_TABLE} p ON p.Z_PK = i.ZSCORE "
            "WHERE i.Z_ENT IN (?, ?) ORDER BY COALESCE(p.ZSORTTITLE, i.ZSORTTITLE) COLLATE NOCASE, "
            "COALESCE(p.Z_PK, i.Z_PK), i.ZSCORE IS NOT NULL, i.ZSTARTPAGE",
            (s.score_entity, s.bookmark_entity),
        )
        return [pk for (pk,) in rows]

    def items(self, pks: Iterable[int] | None = None) -> list[Item]:
        wanted = list(self.item_pks() if pks is None else pks)
        values = {kind: self._values_by_item(kind) for kind in MetaKind}
        rating, difficulty = self.schema.scales["rating"], self.schema.scales["difficulty"]
        rows = {
            row[0]: row
            for row in self.conn.execute(
                f"SELECT i.Z_PK, i.ZUUID, i.ZTITLE, i.Z_ENT, p.ZTITLE, i.ZSTARTPAGE, i.ZENDPAGE, "
                f"i.ZREFERENCE, i.ZKEY, r.{rating.value_column}, d.{difficulty.value_column}, "
                f"i.ZMINUTES, i.ZSECONDS, COALESCE(i.ZPATH, p.ZPATH) FROM {ITEM_TABLE} i "
                f"LEFT JOIN {ITEM_TABLE} p ON p.Z_PK = i.ZSCORE "
                f"LEFT JOIN {META_TABLE} r ON r.Z_PK = i.{rating.item_column} "
                f"LEFT JOIN {META_TABLE} d ON d.Z_PK = i.{difficulty.item_column} "
                "WHERE i.Z_ENT IN (?, ?)",
                (self.schema.score_entity, self.schema.bookmark_entity),
            )
        }
        result = []
        for pk in wanted:
            _, uuid, title, ent, parent, start, end, ref, key, rate, diff, mins, secs, path = rows[
                pk
            ]
            bookmark = ent == self.schema.bookmark_entity
            result.append(
                Item(
                    uuid=uuid,
                    title=title or "",
                    kind=ItemKind.BOOKMARK if bookmark else ItemKind.SCORE,
                    parent=parent if bookmark else None,
                    pages=_pages(start, end) if bookmark else None,
                    reference=ref or None,
                    key=_decode_key(key),
                    rating=rate or None,
                    difficulty=diff or None,
                    duration=format_duration(mins, secs),
                    path=path,
                    **{kind.value: values[kind].get(pk, []) for kind in MetaKind},
                )
            )
        return result

    def item(self, pk: int) -> Item:
        return self.items([pk])[0]

    def find(self, match: str) -> int:
        """Resolve a UUID, an exact title, or "Score › Bookmark" to an item's primary key."""
        s = self.schema
        base = (
            f"SELECT i.Z_PK, i.ZTITLE, p.ZTITLE FROM {ITEM_TABLE} i "
            f"LEFT JOIN {ITEM_TABLE} p ON p.Z_PK = i.ZSCORE WHERE i.Z_ENT IN (?, ?) AND "
        )
        ents = (s.score_entity, s.bookmark_entity)
        rows = self.conn.execute(base + "i.ZUUID = ?", (*ents, match)).fetchall()
        if not rows:
            parts = _PATH_SEPARATOR.split(match.strip(), maxsplit=1)
            if len(parts) == 2:
                rows = self.conn.execute(
                    base + "p.ZTITLE = ? COLLATE NOCASE AND i.ZTITLE = ? COLLATE NOCASE",
                    (*ents, *parts),
                ).fetchall()
            if not rows:
                rows = self.conn.execute(
                    base + "i.ZTITLE = ? COLLATE NOCASE", (*ents, match)
                ).fetchall()
        if not rows:
            raise NotFoundError(f"No score or bookmark with UUID or title {match!r}.")
        if len(rows) > 1:
            names = ", ".join(f"{p} › {t}" if p else t for _, t, p in rows)
            raise ChangesetError(
                f"{match!r} matches {len(rows)} items ({names}); "
                "use 'Score › Bookmark' or the UUID."
            )
        return rows[0][0]

    def values(self, kind: MetaKind) -> list[MetaValue]:
        k = self.schema.kinds[kind]
        sort = "m.ZLAST" if kind is MetaKind.COMPOSERS else "NULL"
        rows = self.conn.execute(
            f"SELECT m.{k.value_column}, COUNT(j.{k.join_item}), {sort} FROM {k.table} m "
            f"LEFT JOIN {k.join_table} j ON j.{k.join_meta} = m.Z_PK "
            f"WHERE m.Z_ENT = ? AND COALESCE(m.{k.value_column}, '') <> '' "
            f"GROUP BY m.Z_PK ORDER BY m.{k.value_column} COLLATE NOCASE",
            (k.entity,),
        )
        return [MetaValue(value, count, sort_name) for value, count, sort_name in rows]

    def setlists(self) -> list[Setlist]:
        result = []
        for pk, title, uuid in self.conn.execute(
            f"SELECT Z_PK, ZTITLE, ZUUID FROM {SETLIST_TABLE} ORDER BY ZTITLE COLLATE NOCASE"
        ).fetchall():
            entries = self.conn.execute(
                f"SELECT ZITEM FROM {SETLIST_ENTRY_TABLE} WHERE ZSETLIST = ? "
                "ORDER BY Z_FOK_SETLIST",
                (pk,),
            ).fetchall()
            members = self.items(item for (item,) in entries if item is not None)
            result.append(Setlist(title or "", uuid or "", [m.name for m in members]))
        return result

    def _values_by_item(self, kind: MetaKind) -> dict[int, list[str]]:
        k = self.schema.kinds[kind]
        result: dict[int, list[str]] = defaultdict(list)
        for item, value in self.conn.execute(
            f"SELECT j.{k.join_item}, m.{k.value_column} FROM {k.join_table} j "
            f"JOIN {k.table} m ON m.Z_PK = j.{k.join_meta} ORDER BY m.Z_PK"
        ):
            if value:
                result[item].append(value)
        return result

    def _meta_pk(self, kind: MetaKind, value: str) -> int | None:
        k = self.schema.kinds[kind]
        row = self.conn.execute(
            f"SELECT Z_PK FROM {k.table} WHERE Z_ENT = ? AND {k.value_column} = ?",
            (k.entity, value),
        ).fetchone()
        return row[0] if row else None

    def _items_with(self, kind: MetaKind, meta_pk: int) -> set[int]:
        k = self.schema.kinds[kind]
        rows = self.conn.execute(
            f"SELECT {k.join_item} FROM {k.join_table} WHERE {k.join_meta} = ?", (meta_pk,)
        )
        return {pk for (pk,) in rows}

    # ---- writes ------------------------------------------------------------------------

    def set_scalar(self, pk: int, name: str, value: object) -> None:
        if name == "title":
            if not isinstance(value, str) or not value.strip():
                raise ChangesetError("A title cannot be empty.")
            self._update_item(pk, ZTITLE=value, ZSORTTITLE=sort_title(value))
        elif name == "reference":
            self._update_item(pk, ZREFERENCE=value or None)
        elif name == "key":
            try:
                self._update_item(pk, ZKEY=keys.encode(str(value)) if value else None)
            except ValueError as exc:
                raise ChangesetError(str(exc)) from exc
        elif name in _SCALE_MAX:
            scale = self.schema.scales[name]
            meta = self._ensure_scale(name, int(str(value))) if value else None
            self._update_item(pk, **{scale.item_column: meta})
        elif name == "duration":
            try:
                minutes, seconds = parse_duration(str(value)) if value else (None, None)
            except ValueError as exc:
                raise ChangesetError(str(exc)) from exc
            self._update_item(pk, ZMINUTES=minutes, ZSECONDS=seconds)
        else:
            raise ChangesetError(f"Unknown field {name!r}.")

    def set_values(self, pk: int, kind: MetaKind, values: list[str]) -> None:
        k = self.schema.kinds[kind]
        self.conn.execute(f"DELETE FROM {k.join_table} WHERE {k.join_item} = ?", (pk,))
        self.add_values(pk, kind, values)

    def add_values(self, pk: int, kind: MetaKind, values: list[str]) -> None:
        k = self.schema.kinds[kind]
        for value in values:
            self.conn.execute(
                f"INSERT OR IGNORE INTO {k.join_table} ({k.join_item}, {k.join_meta}) "
                "VALUES (?, ?)",
                (pk, self._ensure_meta(kind, value)),
            )

    def remove_values(self, pk: int, kind: MetaKind, values: list[str]) -> None:
        k = self.schema.kinds[kind]
        for value in values:
            meta_pk = self._meta_pk(kind, value)
            if meta_pk is not None:
                self.conn.execute(
                    f"DELETE FROM {k.join_table} WHERE {k.join_item} = ? AND {k.join_meta} = ?",
                    (pk, meta_pk),
                )

    def rename(self, kind: MetaKind, old: str, new: str) -> set[int] | None:
        """Rename a value everywhere; merges into ``new`` if it already exists.

        Returns the affected items, or None if ``old`` is gone but ``new`` exists (already done).
        """
        if kind is MetaKind.LIBRARIES:
            raise ChangesetError("Rename libraries in forScore itself.")
        old_pk = self._meta_pk(kind, old)
        if old_pk is None:
            if self._meta_pk(kind, new) is not None:
                return None
            raise NotFoundError(f"No {kind.value[:-1]} called {old!r}.")
        items = self._items_with(kind, old_pk)
        existing = self._meta_pk(kind, new)
        if existing is None or existing == old_pk:
            k = self.schema.kinds[kind]
            extra = ", ZLAST = ?" if kind is MetaKind.COMPOSERS else ""
            params = (new, _last_name(new)) if extra else (new,)
            self.conn.execute(
                f"UPDATE {META_TABLE} SET {k.value_column} = ?{extra}, Z_OPT = Z_OPT + 1 "
                "WHERE Z_PK = ?",
                (*params, old_pk),
            )
        else:
            for pk in items:
                self.add_values(pk, kind, [new])
            self._delete_meta(kind, old_pk)
        return items

    def set_sort_name(self, composer: str, sort_name: str) -> bool:
        """Set a composer's sort name (ZLAST). Returns False if it already had that value."""
        meta_pk = self._meta_pk(MetaKind.COMPOSERS, composer)
        if meta_pk is None:
            raise NotFoundError(f"No composer called {composer!r}.")
        cursor = self.conn.execute(
            f"UPDATE {META_TABLE} SET ZLAST = ?, Z_OPT = Z_OPT + 1 "
            "WHERE Z_PK = ? AND COALESCE(ZLAST, '') <> ?",
            (sort_name, meta_pk, sort_name),
        )
        return cursor.rowcount > 0

    def prune(self, kind: MetaKind) -> list[str]:
        """Delete values no item uses any more; returns their names. Never prunes libraries."""
        if kind is MetaKind.LIBRARIES:
            return []
        k = self.schema.kinds[kind]
        orphans = self.conn.execute(
            f"SELECT Z_PK, {k.value_column} FROM {META_TABLE} WHERE Z_ENT = ? AND Z_PK NOT IN "
            f"(SELECT {k.join_meta} FROM {k.join_table}) AND COALESCE({k.value_column}, '') <> ''",
            (k.entity,),
        ).fetchall()
        for meta_pk, _ in orphans:
            self._delete_meta(kind, meta_pk)
        return [value for _, value in orphans]

    def touch(self, pks: Iterable[int]) -> None:
        """Bump Core Data's version and modification date on changed items."""
        now = core_data_now()
        for pk in pks:
            self.conn.execute(
                f"UPDATE {ITEM_TABLE} SET Z_OPT = COALESCE(Z_OPT, 0) + 1, ZMODIFIED = ? "
                "WHERE Z_PK = ?",
                (now, pk),
            )

    def _update_item(self, pk: int, **columns: object) -> None:
        assignments = ", ".join(f"{name} = ?" for name in columns)
        self.conn.execute(
            f"UPDATE {ITEM_TABLE} SET {assignments} WHERE Z_PK = ?", (*columns.values(), pk)
        )

    def _next_meta_pk(self) -> int:
        (pk,) = self.conn.execute(
            "SELECT Z_MAX + 1 FROM Z_PRIMARYKEY WHERE Z_ENT = ?", (self.schema.meta_entity,)
        ).fetchone()
        self.conn.execute(
            "UPDATE Z_PRIMARYKEY SET Z_MAX = ? WHERE Z_ENT = ?", (pk, self.schema.meta_entity)
        )
        return pk

    def _insert_meta(self, columns: dict[str, object]) -> None:
        self.conn.execute(
            f"INSERT INTO {META_TABLE} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))})",
            tuple(columns.values()),
        )

    def _ensure_meta(self, kind: MetaKind, value: str) -> int:
        value = value.strip()
        if not value:
            raise ChangesetError(f"Empty {kind.value[:-1]} value.")
        existing = self._meta_pk(kind, value)
        if existing is not None:
            return existing
        if kind is MetaKind.LIBRARIES:
            raise ChangesetError(f"No library called {value!r}; create it in forScore first.")
        k = self.schema.kinds[kind]
        pk = self._next_meta_pk()
        columns: dict[str, object] = {"Z_PK": pk, "Z_ENT": k.entity, "Z_OPT": 1}
        columns[k.value_column] = value
        if kind is MetaKind.COMPOSERS:
            columns["ZLAST"] = _last_name(value)
        self._insert_meta(columns)
        return pk

    def _ensure_scale(self, name: str, value: int) -> int:
        if not 1 <= value <= _SCALE_MAX[name]:
            raise ChangesetError(f"{name} must be between 0 and {_SCALE_MAX[name]}.")
        scale = self.schema.scales[name]
        row = self.conn.execute(
            f"SELECT Z_PK FROM {META_TABLE} WHERE Z_ENT = ? AND {scale.value_column} = ?",
            (scale.entity, value),
        ).fetchone()
        if row:
            return row[0]
        pk = self._next_meta_pk()
        self._insert_meta(
            {"Z_PK": pk, "Z_ENT": scale.entity, "Z_OPT": 1, scale.value_column: value}
        )
        return pk

    def _delete_meta(self, kind: MetaKind, meta_pk: int) -> None:
        k = self.schema.kinds[kind]
        self.conn.execute(f"DELETE FROM {k.join_table} WHERE {k.join_meta} = ?", (meta_pk,))
        self.conn.execute(f"DELETE FROM {META_TABLE} WHERE Z_PK = ?", (meta_pk,))


def _last_name(name: str) -> str:
    return name.split()[-1]
