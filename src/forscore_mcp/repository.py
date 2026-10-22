"""Read and write primitives on an open library connection.

Writes here are low-level and do no safety checks of their own; callers go through
`library.Library`, which adds guards, backups and transactions.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable

from . import keys
from .db import core_data_now
from .errors import ChangesetError, NotFoundError
from .models import MetaKind, MetaValue, Score
from .schema import ITEM_TABLE, META_TABLE, Schema
from .sorttitle import sort_title


def _decode_key(code: object) -> str | None:
    if code in (None, "", 0):
        return None
    try:
        return keys.decode(int(str(code)))
    except ValueError:
        return f"unknown ({code})"


class Store:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.schema = Schema.load(conn)

    # ---- reads -------------------------------------------------------------------------

    def score_pks(self) -> list[int]:
        rows = self.conn.execute(
            f"SELECT Z_PK FROM {ITEM_TABLE} WHERE Z_ENT = ? ORDER BY ZSORTTITLE COLLATE NOCASE",
            (self.schema.score_entity,),
        )
        return [pk for (pk,) in rows]

    def scores(self, pks: Iterable[int] | None = None) -> list[Score]:
        wanted = list(self.score_pks() if pks is None else pks)
        values = {kind: self._values_by_item(kind) for kind in MetaKind}
        rows = {
            row[0]: row
            for row in self.conn.execute(
                f"SELECT Z_PK, ZUUID, ZTITLE, ZREFERENCE, ZKEY, ZPATH FROM {ITEM_TABLE} "
                "WHERE Z_ENT = ?",
                (self.schema.score_entity,),
            )
        }
        return [
            Score(
                uuid=rows[pk][1],
                title=rows[pk][2] or "",
                reference=rows[pk][3] or None,
                key=_decode_key(rows[pk][4]),
                path=rows[pk][5],
                **{kind.value: values[kind].get(pk, []) for kind in MetaKind},
            )
            for pk in wanted
        ]

    def score(self, pk: int) -> Score:
        return self.scores([pk])[0]

    def find(self, match: str) -> int:
        """Resolve a UUID or (case-insensitive, exact) title to a score's primary key."""
        rows = self.conn.execute(
            f"SELECT Z_PK, ZTITLE FROM {ITEM_TABLE} WHERE Z_ENT = ? "
            "AND (ZUUID = ? OR ZTITLE = ? COLLATE NOCASE)",
            (self.schema.score_entity, match, match),
        ).fetchall()
        if not rows:
            raise NotFoundError(f"No score with UUID or title {match!r}.")
        if len(rows) > 1:
            raise ChangesetError(f"Title {match!r} matches {len(rows)} scores; use the UUID.")
        return rows[0][0]

    def values(self, kind: MetaKind) -> list[MetaValue]:
        k = self.schema.kinds[kind]
        rows = self.conn.execute(
            f"SELECT m.{k.value_column}, COUNT(j.{k.join_item}) FROM {META_TABLE} m "
            f"LEFT JOIN {k.join_table} j ON j.{k.join_meta} = m.Z_PK "
            f"WHERE m.Z_ENT = ? AND COALESCE(m.{k.value_column}, '') <> '' "
            f"GROUP BY m.Z_PK ORDER BY m.{k.value_column} COLLATE NOCASE",
            (k.entity,),
        )
        return [MetaValue(value, count) for value, count in rows]

    def _values_by_item(self, kind: MetaKind) -> dict[int, list[str]]:
        k = self.schema.kinds[kind]
        result: dict[int, list[str]] = defaultdict(list)
        for item, value in self.conn.execute(
            f"SELECT j.{k.join_item}, m.{k.value_column} FROM {k.join_table} j "
            f"JOIN {META_TABLE} m ON m.Z_PK = j.{k.join_meta} ORDER BY m.Z_PK"
        ):
            if value:
                result[item].append(value)
        return result

    def _meta_pk(self, kind: MetaKind, value: str) -> int | None:
        k = self.schema.kinds[kind]
        row = self.conn.execute(
            f"SELECT Z_PK FROM {META_TABLE} WHERE Z_ENT = ? AND {k.value_column} = ?",
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

    def set_scalar(self, pk: int, field: str, value: str | None) -> None:
        if field == "title":
            if not value:
                raise ChangesetError("A title cannot be empty.")
            self._update_item(pk, ZTITLE=value, ZSORTTITLE=sort_title(value))
        elif field == "reference":
            self._update_item(pk, ZREFERENCE=value or None)
        elif field == "key":
            try:
                self._update_item(pk, ZKEY=keys.encode(value) if value else None)
            except ValueError as exc:
                raise ChangesetError(str(exc)) from exc
        else:
            raise ChangesetError(f"Unknown field {field!r}.")

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

    def rename(self, kind: MetaKind, old: str, new: str) -> set[int]:
        """Rename a value everywhere; merges into ``new`` if it already exists."""
        old_pk = self._meta_pk(kind, old)
        if old_pk is None:
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

    def prune(self, kind: MetaKind) -> list[str]:
        """Delete values no score uses any more; returns their names."""
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
        """Bump Core Data's version and modification date so forScore syncs the items."""
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

    def _ensure_meta(self, kind: MetaKind, value: str) -> int:
        value = value.strip()
        if not value:
            raise ChangesetError(f"Empty {kind.value[:-1]} value.")
        existing = self._meta_pk(kind, value)
        if existing is not None:
            return existing
        k = self.schema.kinds[kind]
        (pk,) = self.conn.execute(
            "SELECT Z_MAX + 1 FROM Z_PRIMARYKEY WHERE Z_ENT = ?", (self.schema.meta_entity,)
        ).fetchone()
        self.conn.execute(
            "UPDATE Z_PRIMARYKEY SET Z_MAX = ? WHERE Z_ENT = ?", (pk, self.schema.meta_entity)
        )
        columns = {"Z_PK": pk, "Z_ENT": k.entity, "Z_OPT": 1, k.value_column: value}
        if kind is MetaKind.COMPOSERS:
            columns["ZLAST"] = _last_name(value)
        self.conn.execute(
            f"INSERT INTO {META_TABLE} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))})",
            tuple(columns.values()),
        )
        return pk

    def _delete_meta(self, kind: MetaKind, meta_pk: int) -> None:
        k = self.schema.kinds[kind]
        self.conn.execute(f"DELETE FROM {k.join_table} WHERE {k.join_meta} = ?", (meta_pk,))
        self.conn.execute(f"DELETE FROM {META_TABLE} WHERE Z_PK = ?", (meta_pk,))


def _last_name(name: str) -> str:
    return name.split()[-1]
