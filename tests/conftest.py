"""Synthetic forScore library built from the real schema DDL (no real user data)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from forscore_mcp import csvimport, paths, safety, syncfiles
from forscore_mcp.library import Library

SCHEMA = Path(__file__).parent / "fixtures" / "schema.sql"
ENTITIES = [
    (1, "Button", 0), (2, "Cylon", 0), (3, "Folder", 0), (4, "Item", 0), (5, "Bookmark", 4),
    (6, "Score", 4), (7, "Library", 0), (9, "Meta", 0), (10, "Composer", 9),
    (11, "Difficulty", 9), (12, "Genre", 9), (13, "Keyword", 9), (14, "Label", 9),
    (15, "Rating", 9), (19, "Setlist", 0),
]  # fmt: skip
# pk, entity, uuid, title, reference, key, parent, start, end, rating meta, minutes, seconds
ITEMS = [
    (1, 6, "UUID-ELISE", "Fur Elise", None, 110, None, None, None, 30, 2, 37),
    (2, 6, "UUID-WALTZ", "Waltz in B Minor", "Op. 69 No.2", *[None] * 7),
    (3, 6, "UUID-WET", "Wet Hands", None, 610, None, None, None, None, None, None),
    (4, 6, "UUID-KINDER", "Kinderszenen", "Op. 15", None, None, None, None, None, None, None),
    (5, 5, "UUID-TRAUM", "Träumerei", None, 410, 4, 7, 7, 30, None, None),
]  # fmt: skip
# pk, entity, column, value
META = [
    (20, 10, "ZVALUE", "Beethoven"), (21, 10, "ZVALUE", "Chopin"), (22, 10, "ZVALUE", "C418"),
    (28, 10, "ZVALUE", "Robert Schumann"),
    (23, 12, "ZVALUE2", "Classical"), (24, 12, "ZVALUE2", "Soundtrack"),
    (25, 13, "ZVALUE3", "Minecraft"), (26, 13, "ZVALUE3", "Unused tag"),
    (27, 14, "ZVALUE4", "Game"),
    (30, 15, "ZVALUE5", 4), (31, 11, "ZVALUE1", 3),
]  # fmt: skip
LIBRARIES = [(1, "Lesson Materials"), (2, "Personal")]
LINKS = [
    ("Z_4COMPOSERS", 1, 20), ("Z_4COMPOSERS", 2, 21), ("Z_4COMPOSERS", 3, 22),
    ("Z_4COMPOSERS", 4, 28), ("Z_4COMPOSERS", 5, 28),
    ("Z_4GENRES", 1, 23), ("Z_4GENRES", 2, 23), ("Z_4GENRES", 3, 24),
    ("Z_4KEYWORDS", 3, 25), ("Z_4LABELS", 3, 27), ("Z_4LIBRARIES", 4, 1),
]  # fmt: skip


def build_library(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text())
    conn.executemany("INSERT INTO Z_PRIMARYKEY VALUES (?, ?, ?, 0)", ENTITIES)
    conn.execute("UPDATE Z_PRIMARYKEY SET Z_MAX = 40 WHERE Z_NAME = 'Meta'")
    for pk, ent, uuid, title, ref, key, parent, start, end, rating, mins, secs in ITEMS:
        conn.execute(
            "INSERT INTO ZITEM (Z_PK, Z_ENT, Z_OPT, ZUUID, ZTITLE, ZSORTTITLE, ZREFERENCE, ZKEY, "
            "ZPATH, ZSCORE, ZSTARTPAGE, ZENDPAGE, ZRATING, ZDIFFICULTY, ZMINUTES, ZSECONDS) "
            "VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pk, ent, uuid, title, title, ref, key,
             "Kinderszenen.pdf" if parent else f"{title}.pdf",  # bookmarks store the PDF too
             parent, start, end, rating, 31 if pk == 1 else None, mins, secs),
        )  # fmt: skip
    for pk, ent, column, value in META:
        columns = {"Z_PK": pk, "Z_ENT": ent, "Z_OPT": 1, column: value}
        if ent == 10:
            columns["ZLAST"] = str(value).split()[-1]
        conn.execute(
            f"INSERT INTO ZMETA ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
            tuple(columns.values()),
        )
    conn.executemany("INSERT INTO ZLIBRARY (Z_PK, Z_ENT, ZTITLE) VALUES (?, 7, ?)", LIBRARIES)
    for table, item, meta in LINKS:
        conn.execute(f"INSERT INTO {table} VALUES (?, ?)", (item, meta))
    conn.execute("INSERT INTO ZSETLIST (Z_PK, Z_ENT, ZTITLE, ZUUID) VALUES (1, 19, 'Gig', 'S1')")
    conn.executemany(
        "INSERT INTO ZCYLON (Z_ENT, ZITEM, ZSETLIST, Z_FOK_SETLIST) VALUES (2, ?, 1, ?)",
        [(3, 2048), (5, 3072)],
    )
    conn.commit()
    conn.close()

    sync = syncfiles.sync_dir(path)
    sync.mkdir()
    for title in ("Fur Elise", "Waltz in B Minor"):  # Wet Hands has no sync file yet
        syncfiles.write(sync / f"{title}.pdf.itm", {"title": title, "pages": [1, 2], "bpm": 90})
    syncfiles.write(
        sync / "Kinderszenen.pdf.itm",
        {
            "title": "Kinderszenen",
            "bookmarks": [{"Identifier": "UUID-TRAUM", "Title": "Träumerei", "First Page": 7}],
        },
    )
    documents = paths.documents_dir(path)
    documents.mkdir(parents=True)
    pdfs = {"Fur Elise.pdf": b"A", "Wet Hands.pdf": b"A", "Kinderszenen.pdf": b"B"}
    for name, content in pdfs.items():
        (documents / name).write_bytes(content)
    return path


@pytest.fixture
def library_file(tmp_path: Path) -> Path:
    # mirror forScore's layout: Data/Library/Preferences/library.4sl next to Data/Documents
    preferences = tmp_path / "Data" / "Library" / "Preferences"
    preferences.mkdir(parents=True)
    return build_library(preferences / "library.4sl")


class DirectLibrary(Library):
    """Writes straight to the database (direct writes on); used by the direct-write tests."""

    def apply(self, data, *, method="direct", deliver=False):  # type: ignore[override]
        return super().apply(data, method=method, deliver=deliver)


@pytest.fixture
def delivered(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Records CSVs handed to forScore instead of opening the app."""
    sent: list[Path] = []
    monkeypatch.setattr(csvimport, "deliver", lambda path: sent.append(path) or True)
    return sent


@pytest.fixture
def environment(
    library_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delivered: list[Path]
) -> None:
    monkeypatch.setattr(safety, "forscore_running", lambda: False)
    monkeypatch.setenv("FORSCORE_LIBRARY", str(library_file))
    monkeypatch.setenv("FORSCORE_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("FORSCORE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv(safety.DIRECT_WRITES_ENV, raising=False)


@pytest.fixture
def library(environment: None, monkeypatch: pytest.MonkeyPatch) -> Library:
    """Direct writes on, direct writes by default (most write tests exercise the store)."""
    monkeypatch.setenv(safety.DIRECT_WRITES_ENV, safety.DIRECT_WRITES_PHRASE)
    return DirectLibrary()


@pytest.fixture
def safe_library(environment: None) -> Library:
    """The default configuration: CSV import only."""
    return Library()
