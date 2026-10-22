"""Bookmarks, rating/difficulty/duration, libraries, filters, setlists, sort names, audit."""

import pytest

from forscore_mcp import syncfiles
from forscore_mcp.errors import ChangesetError
from forscore_mcp.library import Filters, Library
from forscore_mcp.models import ItemKind, MetaKind


def sync_file(library: Library, pdf: str) -> dict:
    return syncfiles.read(library.sync_dir / f"{pdf}.itm")


# ---- reading -------------------------------------------------------------------------------


def test_bookmark_read(library: Library) -> None:
    bookmark = library.item("Kinderszenen › Träumerei")
    assert bookmark.kind is ItemKind.BOOKMARK
    assert (bookmark.parent, bookmark.pages, bookmark.key) == ("Kinderszenen", "7", "F major")
    assert bookmark.rating == 4
    assert bookmark.composers == ["Robert Schumann"]
    assert library.item("Träumerei") == bookmark  # unique title
    assert library.item("kinderszenen > träumerei") == bookmark


def test_scalars_read(library: Library) -> None:
    elise = library.item("Fur Elise")
    assert (elise.rating, elise.difficulty, elise.duration) == (4, 3, "2:37")
    assert library.item("Kinderszenen").libraries == ["Lesson Materials"]


def test_ambiguous_title(library: Library) -> None:
    library.apply({"items": [{"match": "Träumerei", "set": {"title": "Kinderszenen"}}]})
    with pytest.raises(ChangesetError, match="use 'Score › Bookmark'"):
        library.item("Kinderszenen")


def test_compact_dict_drops_empty_fields(library: Library) -> None:
    data = library.item("Wet Hands").to_dict(compact=True)
    assert data == {
        "name": "Wet Hands", "uuid": "UUID-WET", "key": "A major", "composers": ["C418"],
        "genres": ["Soundtrack"], "tags": ["Minecraft"], "labels": ["Game"],
        "path": "Wet Hands.pdf",
    }  # fmt: skip


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (Filters(kind=ItemKind.BOOKMARK), ["Kinderszenen › Träumerei"]),
        (Filters(composer="robert schumann", kind=ItemKind.SCORE), ["Kinderszenen"]),
        (Filters(genre="Classical"), ["Fur Elise", "Waltz in B Minor"]),
        (Filters(library="Lesson Materials"), ["Kinderszenen"]),
        (Filters(missing="genres", kind=ItemKind.SCORE), ["Kinderszenen"]),
        (Filters(query="träum"), ["Kinderszenen › Träumerei"]),
    ],
)
def test_filters(library: Library, filters: Filters, expected: list[str]) -> None:
    assert [i.name for i in library.items(filters)] == expected


def test_unknown_missing_field(library: Library) -> None:
    with pytest.raises(ValueError, match="Unknown field"):
        library.items(Filters(missing="colour"))


def test_paging(library: Library) -> None:
    page = library.page(offset=1, limit=2)
    assert page.total == 5
    assert [i.name for i in page.items] == ["Kinderszenen", "Kinderszenen › Träumerei"]


def test_setlists(library: Library) -> None:
    (gig,) = library.setlists()
    assert (gig.title, gig.items) == ("Gig", ["Wet Hands", "Kinderszenen › Träumerei"])


def test_values_include_sort_names_and_libraries(library: Library) -> None:
    composers = {v.value: v.sort_name for v in library.values(MetaKind.COMPOSERS)}
    assert composers["Robert Schumann"] == "Schumann"
    libraries = {v.value: v.count for v in library.values(MetaKind.LIBRARIES)}
    assert libraries == {"Lesson Materials": 1, "Personal": 0}


# ---- writing -------------------------------------------------------------------------------


def test_edit_bookmark_updates_its_sync_entry(library: Library) -> None:
    report = library.apply(
        {
            "items": [
                {
                    "match": "Kinderszenen › Träumerei",
                    "set": {"reference": "Op. 15 No. 7", "rating": 5, "difficulty": 2},
                    "add": {"tags": ["Favourites"]},
                }
            ]
        }
    )
    assert report.sync_files_updated == 1
    (entry,) = sync_file(library, "Kinderszenen.pdf")["bookmarks"]
    assert entry["Reference"] == "Op. 15 No. 7"
    assert (entry["Rating"], entry["Difficulty"], entry["Key"]) == (5, 2, 410)
    assert entry["Keyword"] == "Favourites"
    assert entry["First Page"] == 7  # untouched
    assert sync_file(library, "Kinderszenen.pdf")["title"] == "Kinderszenen"
    assert not [d for d in library.sync_drift() if d.item == "Kinderszenen › Träumerei"]


def test_rating_difficulty_duration(library: Library) -> None:
    library.apply(
        {
            "items": [
                {
                    "match": "Waltz in B Minor",
                    "set": {"rating": 4, "difficulty": 1, "duration": "3:05"},
                }
            ]
        }
    )
    waltz = library.item("Waltz in B Minor")
    assert (waltz.rating, waltz.difficulty, waltz.duration) == (4, 1, "3:05")
    data = sync_file(library, "Waltz in B Minor.pdf")
    assert (data["rating"], data["difficulty"], data["minutes"], data["seconds"]) == (4, 1, 3, 5)
    library.apply(
        {
            "items": [
                {
                    "match": "Waltz in B Minor",
                    "set": {"rating": 0, "difficulty": None, "duration": None},
                }
            ]
        }
    )
    waltz = library.item("Waltz in B Minor")
    assert (waltz.rating, waltz.difficulty, waltz.duration) == (None, None, None)
    assert "rating" not in sync_file(library, "Waltz in B Minor.pdf")


@pytest.mark.parametrize(
    "updates",
    [{"rating": 6}, {"difficulty": 4}, {"rating": "5"}, {"rating": True}, {"duration": "3m"}],
)
def test_bad_scalars(library: Library, updates: dict) -> None:
    with pytest.raises(ChangesetError):
        library.preview({"items": [{"match": "Wet Hands", "set": updates}]})


def test_libraries(library: Library) -> None:
    report = library.apply(
        {"items": [{"match": "Kinderszenen", "set": {"libraries": ["Personal"]}}], "prune": True}
    )
    assert library.item("Kinderszenen").libraries == ["Personal"]
    assert sync_file(library, "Kinderszenen.pdf")["libraries"] == "Personal"
    assert "libraries" not in report.pruned  # libraries are never pruned
    assert {v.value for v in library.values(MetaKind.LIBRARIES)} == {"Lesson Materials", "Personal"}


def test_libraries_cannot_be_created_or_renamed(library: Library) -> None:
    with pytest.raises(ChangesetError, match="create it in forScore"):
        library.preview({"items": [{"match": "Wet Hands", "add": {"libraries": ["New"]}}]})
    with pytest.raises(ChangesetError, match="Rename libraries in forScore"):
        library.preview({"renames": {"libraries": {"Personal": "Mine"}}})


def test_sort_names(library: Library) -> None:
    report = library.apply({"sort_names": {"Robert Schumann": "Schumann, Robert"}})
    assert report.sort_names == {"Robert Schumann": "Schumann, Robert"}
    composers = {v.value: v.sort_name for v in library.values(MetaKind.COMPOSERS)}
    assert composers["Robert Schumann"] == "Schumann, Robert"
    assert library.preview({"sort_names": {"Robert Schumann": "Schumann, Robert"}}).empty


def test_scores_alias(library: Library) -> None:
    report = library.preview({"scores": [{"match": "Wet Hands", "set": {"key": "A minor"}}]})
    assert report.changes["Wet Hands"]["key"] == ["A major", "A minor"]
    with pytest.raises(ChangesetError):
        library.preview({"scores": [], "items": []})


# ---- audit ---------------------------------------------------------------------------------


def test_audit(library: Library) -> None:
    library.apply(
        {
            "items": [{"match": "Waltz in B Minor", "set": {"title": "Wet hands!"}}],
            "renames": {"composers": {"C418": "Manuel de Falla"}},
        }
    )
    report = library.audit()
    assert report.duplicate_titles == [["Wet Hands", "Wet hands!"]]
    assert report.identical_files == [["Fur Elise", "Wet Hands"]]
    assert {"item": "Wet hands!", "file": "Waltz in B Minor.pdf"} in report.filename_mismatches
    assert [s["composer"] for s in report.sort_names] == ["Manuel de Falla"]


def test_example_changeset_is_valid(library: Library) -> None:
    import json
    from pathlib import Path

    example = Path(__file__).parent.parent / "examples" / "changeset.example.json"
    from forscore_mcp import changeset

    parsed = changeset.parse(json.loads(example.read_text()))
    assert len(parsed.items) == 3
