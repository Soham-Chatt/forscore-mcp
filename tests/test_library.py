import sqlite3
from pathlib import Path
from typing import Any

import pytest

from forscore_mcp import safety
from forscore_mcp.errors import (
    AppRunningError,
    ChangesetError,
    LibraryNotFoundError,
    NotFoundError,
    SchemaError,
)
from forscore_mcp.library import Library
from forscore_mcp.models import MetaKind

ELISE: dict[str, Any] = {
    "match": "fur elise",
    "set": {"title": "Für Elise", "reference": "WoO 59", "key": "A minor"},
    "add": {"tags": ["ABRSM Grade 5"]},
}
CLEANUP: dict[str, Any] = {
    "renames": {"composers": {"Beethoven": "Ludwig van Beethoven"}},
    "scores": [
        ELISE,
        {
            "match": "UUID-WALTZ",
            "set": {"composers": ["Frédéric Chopin"], "genres": ["Romantic"]},
        },
    ],
}


def test_reads(library: Library) -> None:
    scores = library.scores()
    assert [s.title for s in scores] == ["Fur Elise", "Waltz in B Minor", "Wet Hands"]
    wet = library.score("Wet Hands")
    assert wet.key == "A major"
    assert wet.tags == ["Minecraft"]
    assert wet.labels == ["Game"]
    assert [s.title for s in library.scores("chopin")] == ["Waltz in B Minor"]
    genres = {v.value: v.count for v in library.values(MetaKind.GENRES)}
    assert genres == {"Classical": 2, "Soundtrack": 1}


def test_score_not_found(library: Library) -> None:
    with pytest.raises(NotFoundError):
        library.score("Nope")


def test_preview_does_not_write(library: Library) -> None:
    report = library.preview(CLEANUP)
    assert report.dry_run
    assert report.changes["Für Elise"]["key"] == ["C major", "A minor"]
    assert report.changes["Für Elise"]["composers"] == [["Beethoven"], ["Ludwig van Beethoven"]]
    assert report.pruned == {"composers": ["Chopin"], "tags": ["Unused tag"]}
    assert library.score("UUID-ELISE").title == "Fur Elise"


def test_apply(library: Library, library_file: Path) -> None:
    report = library.apply(CLEANUP)
    assert not report.dry_run
    assert report.backup is not None
    elise = library.score("UUID-ELISE")
    assert (elise.title, elise.reference, elise.key) == ("Für Elise", "WoO 59", "A minor")
    assert elise.composers == ["Ludwig van Beethoven"]
    assert elise.tags == ["ABRSM Grade 5"]
    waltz = library.score("UUID-WALTZ")
    assert (waltz.composers, waltz.genres) == (["Frédéric Chopin"], ["Romantic"])

    with sqlite3.connect(library_file) as conn:
        opt, modified, sort = conn.execute(
            "SELECT Z_OPT, ZMODIFIED, ZSORTTITLE FROM ZITEM WHERE Z_PK = 1"
        ).fetchone()
        untouched = conn.execute("SELECT Z_OPT, ZMODIFIED FROM ZITEM WHERE Z_PK = 3").fetchone()
        last = conn.execute("SELECT ZLAST FROM ZMETA WHERE ZVALUE = 'Frédéric Chopin'").fetchone()
        max_pk = conn.execute("SELECT Z_MAX FROM Z_PRIMARYKEY WHERE Z_NAME = 'Meta'").fetchone()
    assert (opt, sort) == (2, "Für Elise")
    assert modified is not None
    assert untouched == (1, None)
    assert last == ("Chopin",)
    assert max_pk[0] > 30


def test_apply_is_idempotent(library: Library) -> None:
    library.apply(CLEANUP)
    second = {"scores": [{**ELISE, "match": "UUID-ELISE"}]}
    assert library.preview(second).empty


def test_rename_merges_into_existing(library: Library) -> None:
    library.apply({"renames": {"genres": {"Soundtrack": "Classical"}}})
    assert {v.value: v.count for v in library.values(MetaKind.GENRES)} == {"Classical": 3}


def test_remove_values(library: Library) -> None:
    library.apply({"scores": [{"match": "Wet Hands", "remove": {"labels": ["Game"]}}]})
    assert library.score("Wet Hands").labels == []
    assert library.values(MetaKind.LABELS) == []


def test_apply_refuses_while_running(library: Library, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(safety, "forscore_running", lambda: True)
    with pytest.raises(AppRunningError):
        library.apply(CLEANUP)
    assert library.backups() == []


def test_bad_changeset_writes_nothing(library: Library) -> None:
    bad = {"scores": [{"match": "Wet Hands", "set": {"key": "H major"}}]}
    with pytest.raises(ChangesetError):
        library.apply(bad)
    assert library.backups() == []
    assert library.score("Wet Hands").key == "A major"


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {"oops": 1},
        {"scores": [{"set": {}}]},
        {"scores": [{"match": "x", "set": {"colour": "red"}}]},
        {"scores": [{"match": "x", "add": {"moods": ["happy"]}}]},
        {"scores": [{"match": "x", "set": {"tags": "not a list"}}]},
        {"renames": {"composers": {"A": ""}}},
        {"prune": "yes"},
    ],
)
def test_changeset_validation(library: Library, bad: object) -> None:
    with pytest.raises(ChangesetError):
        library.preview(bad)


def test_backup_and_restore(library: Library) -> None:
    first = library.backup()
    library.apply(CLEANUP)
    safety_copy = library.restore(first.id)
    assert library.score("UUID-ELISE").title == "Fur Elise"
    assert {b.id for b in library.backups()} >= {first.id, safety_copy.id}
    with pytest.raises(NotFoundError):
        library.restore("missing")


def test_missing_library(tmp_path: Path) -> None:
    with pytest.raises(LibraryNotFoundError):
        Library(tmp_path / "nope.4sl").scores()


def test_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "other.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE t (x)")
    with pytest.raises(SchemaError):
        Library(path).scores()
