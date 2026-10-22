import pytest

from forscore_mcp import syncfiles
from forscore_mcp.errors import ChangesetError
from forscore_mcp.library import Library

CHANGE = {
    "scores": [
        {
            "match": "Fur Elise",
            "set": {"title": "Für Elise", "reference": "WoO 59", "key": "A minor"},
            "add": {"tags": ["ABRSM Grade 5", "Classics"]},
        }
    ]
}


def elise_file(library: Library) -> dict:
    return syncfiles.read(library.sync_dir / "Fur Elise.pdf.itm")


def test_fresh_fixture_drifts(library: Library) -> None:
    fields = {(d.item, d.field) for d in library.sync_drift()}
    assert ("Fur Elise", "composer") in fields
    assert ("Wet Hands", "composer") not in fields  # no sync file: nothing to compare


def test_apply_writes_sync_file(library: Library) -> None:
    report = library.apply(CHANGE)
    assert report.sync_files_updated == 1
    data = elise_file(library)
    assert data["title"] == "Für Elise"
    assert data["reference"] == "WoO 59"
    assert data["key"] == 611
    assert data["keywords"] == "ABRSM Grade 5, Classics"
    assert data["composer"] == "Beethoven"
    assert (data["pages"], data["bpm"]) == ([1, 2], 90)  # unrelated keys are kept
    assert "Für Elise" not in {d.item for d in library.sync_drift()}


def test_empty_values_remove_keys(library: Library) -> None:
    library.apply({"scores": [{"match": "Fur Elise", "set": {"genres": []}}]})
    assert "genre" not in elise_file(library)


def test_list_order_is_not_drift(library: Library) -> None:
    library.apply({"scores": [{"match": "Fur Elise", "add": {"composers": ["Anon"]}}]})
    path = library.sync_dir / "Fur Elise.pdf.itm"
    data = syncfiles.read(path)
    data["composer"] = "Anon, Beethoven"
    syncfiles.write(path, data)
    assert "Fur Elise" not in {d.item for d in library.sync_drift()}


def test_preview_leaves_sync_files_alone(library: Library) -> None:
    before = elise_file(library)
    library.preview(CHANGE)
    assert elise_file(library) == before


def test_failed_sync_write_rolls_back(library: Library, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: object) -> bool:
        raise OSError("disk full")

    monkeypatch.setattr(syncfiles, "update", boom)
    with pytest.raises(OSError):
        library.apply(CHANGE)
    assert library.item("UUID-ELISE").title == "Fur Elise"
    assert elise_file(library)["title"] == "Fur Elise"


def test_restore_restores_sync_files(library: Library) -> None:
    report = library.apply(CHANGE)
    assert report.backup is not None
    library.restore(report.backup)
    assert elise_file(library)["title"] == "Fur Elise"


def test_bad_changeset_touches_no_sync_file(library: Library) -> None:
    before = elise_file(library)
    with pytest.raises(ChangesetError):
        library.apply({"scores": [{"match": "Fur Elise", "set": {"key": "H"}}]})
    assert elise_file(library) == before
