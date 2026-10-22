"""Reverse-engineered layout of forScore's Core Data store, validated at runtime.

Entity ids (Z_ENT) and join-table column names are read from the database instead of being
hard-coded, so small Core Data model changes do not break the tool. Anything unexpected
raises SchemaError rather than guessing. See docs/schema.md for details.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .errors import SchemaError
from .models import MetaKind

ITEM_TABLE = "ZITEM"
META_TABLE = "ZMETA"
LIBRARY_TABLE = "ZLIBRARY"
SETLIST_TABLE = "ZSETLIST"
SETLIST_ENTRY_TABLE = "ZCYLON"
REQUIRED_COLUMNS = {
    ITEM_TABLE: (
        "Z_PK", "Z_ENT", "Z_OPT", "ZKEY", "ZMODIFIED", "ZPATH", "ZREFERENCE", "ZSORTTITLE",
        "ZTITLE", "ZUUID", "ZSCORE", "ZSTARTPAGE", "ZENDPAGE", "ZRATING", "ZDIFFICULTY",
        "ZMINUTES", "ZSECONDS",
    ),
    META_TABLE: (
        "Z_PK", "Z_ENT", "Z_OPT", "ZLAST", "ZVALUE", "ZVALUE1", "ZVALUE2", "ZVALUE3", "ZVALUE4",
        "ZVALUE5",
    ),
    LIBRARY_TABLE: ("Z_PK", "Z_ENT", "ZTITLE"),
    SETLIST_TABLE: ("Z_PK", "ZTITLE", "ZUUID"),
    SETLIST_ENTRY_TABLE: ("ZITEM", "ZSETLIST", "Z_FOK_SETLIST"),
}  # fmt: skip

# Per kind: Core Data entity, table and column holding its text, join-table suffix.
_KIND_LAYOUT = {
    MetaKind.COMPOSERS: ("Composer", META_TABLE, "ZVALUE", "COMPOSERS"),
    MetaKind.GENRES: ("Genre", META_TABLE, "ZVALUE2", "GENRES"),
    MetaKind.TAGS: ("Keyword", META_TABLE, "ZVALUE3", "KEYWORDS"),
    MetaKind.LABELS: ("Label", META_TABLE, "ZVALUE4", "LABELS"),
    MetaKind.LIBRARIES: ("Library", LIBRARY_TABLE, "ZTITLE", "LIBRARIES"),
}
# Rating and difficulty: ZITEM column -> ZMETA row (entity) whose integer column holds the value.
_SCALE_LAYOUT = {"rating": ("Rating", "ZVALUE5", "ZRATING"),
                 "difficulty": ("Difficulty", "ZVALUE1", "ZDIFFICULTY")}  # fmt: skip


@dataclass(frozen=True)
class KindSchema:
    entity: int
    table: str
    value_column: str
    join_table: str
    join_item: str
    join_meta: str


@dataclass(frozen=True)
class ScaleSchema:
    entity: int
    value_column: str
    item_column: str


@dataclass(frozen=True)
class Schema:
    item_entity: int
    score_entity: int
    bookmark_entity: int
    meta_entity: int
    kinds: dict[MetaKind, KindSchema]
    scales: dict[str, ScaleSchema]

    @classmethod
    def load(cls, conn: sqlite3.Connection) -> Schema:
        try:
            entities = dict(conn.execute("SELECT Z_NAME, Z_ENT FROM Z_PRIMARYKEY"))
        except sqlite3.DatabaseError as exc:
            raise SchemaError(f"Not a forScore library ({exc}).") from exc

        def entity(name: str) -> int:
            if name not in entities:
                raise SchemaError(f"Unsupported forScore library: entity {name!r} is missing.")
            return entities[name]

        for table, columns in REQUIRED_COLUMNS.items():
            _require_columns(conn, table, columns)
        item = entity("Item")
        kinds = {}
        for kind, (name, table, value_column, suffix) in _KIND_LAYOUT.items():
            ent = entity(name)
            join = f"Z_{item}{suffix}"
            columns = _columns(conn, join)
            item_col = next((c for c in columns if c.startswith(f"Z_{item}ITEMS")), None)
            meta_col = f"Z_{ent}{suffix}"
            if item_col is None or meta_col not in columns:
                raise SchemaError(f"Unsupported forScore library: join table {join} changed.")
            kinds[kind] = KindSchema(ent, table, value_column, join, item_col, meta_col)
        scales = {
            name: ScaleSchema(entity(ent), value_column, item_column)
            for name, (ent, value_column, item_column) in _SCALE_LAYOUT.items()
        }
        return cls(item, entity("Score"), entity("Bookmark"), entity("Meta"), kinds, scales)


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _require_columns(conn: sqlite3.Connection, table: str, required: tuple[str, ...]) -> None:
    missing = set(required) - set(_columns(conn, table))
    if missing:
        raise SchemaError(f"Unsupported forScore library: {table} lacks {sorted(missing)}.")
