"""Synthetic forScore library built from the real schema DDL (no real user data)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from forscore_mcp import safety, syncfiles
from forscore_mcp.library import Library

SCHEMA = Path(__file__).parent / "fixtures" / "schema.sql"
ENTITIES = [
    (1, "Button", 0), (3, "Folder", 0), (4, "Item", 0), (5, "Bookmark", 4), (6, "Score", 4),
    (9, "Meta", 0), (10, "Composer", 9), (11, "Difficulty", 9), (12, "Genre", 9),
    (13, "Keyword", 9), (14, "Label", 9),
]  # fmt: skip
# pk, uuid, title, reference, key code
SCORES = [
    (1, "UUID-ELISE", "Fur Elise", None, 110),
    (2, "UUID-WALTZ", "Waltz in B Minor", "Op. 69 No.2", None),
    (3, "UUID-WET", "Wet Hands", None, 610),
]
# pk, entity, column, value
META = [
    (20, 10, "ZVALUE", "Beethoven"), (21, 10, "ZVALUE", "Chopin"), (22, 10, "ZVALUE", "C418"),
    (23, 12, "ZVALUE2", "Classical"), (24, 12, "ZVALUE2", "Soundtrack"),
    (25, 13, "ZVALUE3", "Minecraft"), (26, 13, "ZVALUE3", "Unused tag"),
    (27, 14, "ZVALUE4", "Game"),
]  # fmt: skip
LINKS = [
    ("Z_4COMPOSERS", 1, 20), ("Z_4COMPOSERS", 2, 21), ("Z_4COMPOSERS", 3, 22),
    ("Z_4GENRES", 1, 23), ("Z_4GENRES", 2, 23), ("Z_4GENRES", 3, 24),
    ("Z_4KEYWORDS", 3, 25), ("Z_4LABELS", 3, 27),
]  # fmt: skip


def build_library(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text())
    conn.executemany("INSERT INTO Z_PRIMARYKEY VALUES (?, ?, ?, 0)", ENTITIES)
    conn.execute("UPDATE Z_PRIMARYKEY SET Z_MAX = 30 WHERE Z_NAME = 'Meta'")
    conn.executemany(
        "INSERT INTO ZITEM (Z_PK, Z_ENT, Z_OPT, ZUUID, ZTITLE, ZSORTTITLE, ZREFERENCE, ZKEY, "
        "ZPATH) VALUES (?, 6, 1, ?, ?, ?, ?, ?, ?)",
        [(pk, uuid, t, t, ref, key, f"{t}.pdf") for pk, uuid, t, ref, key in SCORES],
    )
    for pk, ent, column, value in META:
        last = ", ZLAST" if ent == 10 else ""
        params = (pk, ent, value, value) if last else (pk, ent, value)
        conn.execute(
            f"INSERT INTO ZMETA (Z_PK, Z_ENT, Z_OPT, {column}{last}) "
            f"VALUES (?, ?, 1, ?{', ?' if last else ''})",
            params,
        )
    for table, item, meta in LINKS:
        conn.execute(f"INSERT INTO {table} VALUES (?, ?)", (item, meta))
    conn.commit()
    conn.close()
    sync = syncfiles.sync_dir(path)
    sync.mkdir()
    for _, _, title, *_ in SCORES[:2]:  # the third score has no sync file yet
        syncfiles.write(sync / f"{title}.pdf.itm", {"title": title, "pages": [1, 2], "bpm": 90})
    return path


@pytest.fixture
def library_file(tmp_path: Path) -> Path:
    return build_library(tmp_path / "library.4sl")


@pytest.fixture
def library(library_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Library:
    monkeypatch.setattr(safety, "forscore_running", lambda: False)
    monkeypatch.setenv("FORSCORE_LIBRARY", str(library_file))
    monkeypatch.setenv("FORSCORE_BACKUP_DIR", str(tmp_path / "backups"))
    return Library()
