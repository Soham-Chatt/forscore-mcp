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
ITEM_COLUMNS = (
    "Z_PK",
    "Z_ENT",
    "Z_OPT",
    "ZKEY",
    "ZMODIFIED",
    "ZPATH",
    "ZREFERENCE",
    "ZSORTTITLE",
    "ZTITLE",
    "ZUUID",
)
META_COLUMNS = ("Z_PK", "Z_ENT", "Z_OPT", "ZLAST", "ZVALUE", "ZVALUE2", "ZVALUE3", "ZVALUE4")

# Per kind: Core Data entity name, ZMETA column holding its text, join-table suffix.
_KIND_LAYOUT = {
    MetaKind.COMPOSERS: ("Composer", "ZVALUE", "COMPOSERS"),
    MetaKind.GENRES: ("Genre", "ZVALUE2", "GENRES"),
    MetaKind.TAGS: ("Keyword", "ZVALUE3", "KEYWORDS"),
    MetaKind.LABELS: ("Label", "ZVALUE4", "LABELS"),
}


@dataclass(frozen=True)
class KindSchema:
    entity: int
    value_column: str
    join_table: str
    join_item: str
    join_meta: str


@dataclass(frozen=True)
class Schema:
    item_entity: int
    score_entity: int
    meta_entity: int
    kinds: dict[MetaKind, KindSchema]

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

        _require_columns(conn, ITEM_TABLE, ITEM_COLUMNS)
        _require_columns(conn, META_TABLE, META_COLUMNS)
        item = entity("Item")
        kinds = {}
        for kind, (name, value_column, suffix) in _KIND_LAYOUT.items():
            ent = entity(name)
            table = f"Z_{item}{suffix}"
            columns = _columns(conn, table)
            item_col = next((c for c in columns if c.startswith(f"Z_{item}ITEMS")), None)
            meta_col = f"Z_{ent}{suffix}"
            if item_col is None or meta_col not in columns:
                raise SchemaError(f"Unsupported forScore library: join table {table} changed.")
            kinds[kind] = KindSchema(ent, value_column, table, item_col, meta_col)
        return cls(item, entity("Score"), entity("Meta"), kinds)


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _require_columns(conn: sqlite3.Connection, table: str, required: tuple[str, ...]) -> None:
    missing = set(required) - set(_columns(conn, table))
    if missing:
        raise SchemaError(f"Unsupported forScore library: {table} lacks {sorted(missing)}.")
