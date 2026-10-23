"""The default write path: forScore's Metadata CSV import."""

import csv
from pathlib import Path
from typing import Any

import pytest

from forscore_mcp import csvimport, keys, safety
from forscore_mcp.errors import DirectWritesDisabledError
from forscore_mcp.library import Library
from forscore_mcp.models import MetaKind

ELISE: dict[str, Any] = {"match": "Fur Elise", "set": {"title": "Für Elise", "reference": "WoO 59",
                                      "key": "A minor", "tags": ["Classics"]}}  # fmt: skip


def rows(path: str) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


def simulate_forscore_import(monkeypatch: pytest.MonkeyPatch, changes: dict) -> None:
    """Stand-in for the user tapping Save in forScore: apply the same values directly."""
    monkeypatch.setenv(safety.DIRECT_WRITES_ENV, safety.DIRECT_WRITES_PHRASE)
    Library().apply(changes, method="direct")
    monkeypatch.delenv(safety.DIRECT_WRITES_ENV)


def test_apply_writes_csv_and_leaves_library_alone(
    safe_library: Library, delivered: list[Path]
) -> None:
    report = safe_library.apply({"items": [ELISE]}).to_dict()
    assert report["method"] == "csv"
    assert report["items_in_csv"] == 1
    assert delivered == [Path(report["csv_file"])]
    assert "Backups › Metadata (CSV) › Import" in report["next_step"]
    (row,) = rows(report["csv_file"])
    assert list(row) == csvimport.HEADER
    assert row["Filename"] == "Fur Elise.pdf"
    assert (row["Title"], row["Reference"], row["Tags"]) == ("Für Elise", "WoO 59", "Classics")
    assert (row["keysf"], row["keymi"]) == ("0", "1")
    assert (row["Composers"], row["Genres"]) == ("Beethoven", "Classical")  # full row
    assert (row["Rating"], row["Difficulty"], row["Minutes"], row["Seconds"]) == (
        "4",
        "3",
        "2",
        "37",
    )
    assert safe_library.item("UUID-ELISE").title == "Fur Elise"
    assert report["pruned"] == {}  # CSV cannot delete values


def test_bookmark_row(safe_library: Library) -> None:
    report = safe_library.apply(
        {"items": [{"match": "Kinderszenen › Träumerei", "set": {"reference": "Op. 15 No. 7"}}]}
    ).to_dict()
    (row,) = rows(report["csv_file"])
    assert row["Filename"] == "Kinderszenen.pdf"
    assert (row["Title"], row["Start Page (Bookmark)"], row["End Page (Bookmark)"]) == (
        "Träumerei", "7", "7",
    )  # fmt: skip


def test_cleared_values_are_empty_cells(safe_library: Library) -> None:
    report = safe_library.apply(
        {"items": [{"match": "Fur Elise", "set": {"rating": 0, "duration": None, "genres": []}}]}
    ).to_dict()
    (row,) = rows(report["csv_file"])
    assert (row["Rating"], row["Minutes"], row["Seconds"], row["Genres"]) == ("0", "", "", "")


def test_unsupported_changes_are_skipped(safe_library: Library) -> None:
    report = safe_library.apply(
        {
            "sort_names": {"Robert Schumann": "Schumann, Robert"},
            "items": [
                {"match": "Kinderszenen", "add": {"libraries": ["Personal"]}},
                {"match": "Wet Hands", "set": {"tags": ["Rock, Pop"]}},
                {"match": "Fur Elise", "set": {"key": "D♯ major", "reference": "WoO 59"}},
            ],
        }
    ).to_dict()
    skipped = report["skipped"]
    assert "library membership" in skipped["Kinderszenen"][0]
    assert "comma" in skipped["Wet Hands"][0]
    assert "D♯ major" in skipped["Fur Elise"][0]
    assert "composer sort names" in skipped
    (row,) = rows(report["csv_file"])  # only Für Elise's reference is importable
    assert (row["Filename"], row["Reference"], row["keysf"]) == ("Fur Elise.pdf", "WoO 59", "0")


def test_nothing_to_import(safe_library: Library, delivered: list[Path]) -> None:
    report = safe_library.apply(
        {"items": [{"match": "Kinderszenen", "add": {"libraries": ["Personal"]}}]}
    )
    assert report.to_dict()["next_step"] == "Nothing to import."
    assert not delivered


def test_verify_and_undo(
    safe_library: Library, delivered: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import_id = safe_library.apply({"items": [ELISE]}).to_dict()["import_id"]
    assert safe_library.verify_import(import_id)["status"] == "not imported yet"

    simulate_forscore_import(
        monkeypatch, {"items": [{**ELISE, "set": {**ELISE["set"], "tags": []}}]}
    )
    partial = safe_library.verify_import(import_id)
    assert partial["status"] == "partly applied; check the mismatches"
    assert [m["field"] for m in partial["mismatches"]] == ["tags"]

    simulate_forscore_import(
        monkeypatch, {"items": [{"match": "UUID-ELISE", "set": {"tags": ["Classics"]}}]}
    )
    assert safe_library.verify_import(import_id) == {
        "import_id": import_id, "status": "imported", "items": 1, "mismatches": [],
    }  # fmt: skip

    undo = safe_library.undo_import(import_id)
    assert delivered[-1] == Path(undo["csv_file"])
    (row,) = rows(undo["csv_file"])
    assert (row["Title"], row["Reference"], row["Tags"], row["keysf"]) == ("Fur Elise", "", "", "0")
    assert safe_library.verify_import(undo["import_id"])["status"] == "not imported yet"


def test_unknown_import(safe_library: Library) -> None:
    with pytest.raises(Exception, match="No import"):
        safe_library.verify_import("nope")


def test_direct_writes_and_restore_need_direct_writes(safe_library: Library) -> None:
    with pytest.raises(DirectWritesDisabledError):
        safe_library.apply({"items": [ELISE]}, method="direct")
    backup = safe_library.backup()  # backups are read-only and always allowed
    with pytest.raises(DirectWritesDisabledError):
        safe_library.restore(backup.id)


def test_unused_values_hidden(safe_library: Library) -> None:
    assert "Unused tag" not in {v.value for v in safe_library.values(MetaKind.TAGS)}
    assert "Unused tag" in {
        v.value for v in safe_library.values(MetaKind.TAGS, include_unused=True)
    }
    assert {v.value for v in safe_library.values(MetaKind.LIBRARIES)} == {
        "Lesson Materials", "Personal",
    }  # fmt: skip


@pytest.mark.parametrize(
    ("name", "signature"),
    [("A minor", (0, 1)), ("G minor", (-2, 1)), ("E♭ major", (-3, 0)), ("F♯ major", (6, 0)),
     ("C♯ minor", (4, 1)), ("A♭ major", (-4, 0)), ("D♯ major", None)],
)  # fmt: skip
def test_key_signature(name: str, signature: tuple[int, int] | None) -> None:
    assert keys.to_signature(name) == signature
    if signature:
        assert keys.from_signature(*signature) == name
