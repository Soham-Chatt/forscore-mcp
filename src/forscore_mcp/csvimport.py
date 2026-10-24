"""Write changes as forScore's own Metadata CSV import (the officially supported path).

forScore imports a CSV from Backups › Metadata › Import, shows a per-field diff and applies
it on Save, handling the database and sync itself. Behaviour verified against forScore 15.2:

- rows match existing scores by ``Filename``; unknown files are ignored (nothing is created)
- only differing cells are applied; an empty cell clears the field; lists replace (", ")
- bookmark rows follow their score's row and are meant as its complete bookmark list (left-out
  bookmarks are deleted). But the import does not match existing bookmarks reliably: even
  re-importing forScore's own unchanged export can show bookmarks as "Added" or as "Updated"
  without changes, and saving such a preview has deleted a bookmark. A score row without
  bookmark rows deletes all its bookmarks. So scores that have bookmarks, and bookmarks
  themselves, are never written to a CSV.
- keys are a MIDI-style signature (``keysf``, ``keymi``), not forScore's internal code

Each generated import is kept with the before- and after-state of its items, so it can be
verified once the user has imported it, and undone with a second CSV.
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from . import keys
from .errors import NotFoundError
from .models import Item, ItemKind

HEADER = [
    "Filename", "Title", "Start Page (Bookmark)", "End Page (Bookmark)", "Composers", "Genres",
    "Tags", "Labels", "Reference", "Rating", "Difficulty", "Minutes", "Seconds", "keysf", "keymi",
]  # fmt: skip
# Item fields a CSV row carries; anything else (libraries, sort names) needs direct writes.
CSV_FIELDS = ("title", "composers", "genres", "tags", "labels", "reference", "rating",
              "difficulty", "duration", "key")  # fmt: skip
_LISTS = {"Composers": "composers", "Genres": "genres", "Tags": "tags", "Labels": "labels"}
STATE_FILE = "state.json"


@dataclass
class PendingImport:
    id: str
    csv_path: Path
    before: list[Item] = field(default_factory=list)
    expected: list[Item] = field(default_factory=list)

    def save(self) -> None:
        state = {
            "id": self.id,
            "csv": self.csv_path.name,
            "before": [i.to_dict() for i in self.before],
            "expected": [i.to_dict() for i in self.expected],
        }
        (self.csv_path.parent / STATE_FILE).write_text(json.dumps(state, ensure_ascii=False))

    @classmethod
    def load(cls, directory: Path, import_id: str) -> PendingImport:
        state_file = directory / import_id / STATE_FILE
        if not state_file.is_file():
            raise NotFoundError(f"No import {import_id!r} in {directory}.")
        state = json.loads(state_file.read_text())
        return cls(
            id=state["id"],
            csv_path=state_file.parent / state["csv"],
            before=[Item.from_dict(d) for d in state["before"]],
            expected=[Item.from_dict(d) for d in state["expected"]],
        )


@dataclass(frozen=True)
class Mismatch:
    item: str
    field: str
    expected: Any
    actual: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


BOOKMARK_REASON = "a score with bookmarks (forScore's CSV import can lose or duplicate them)"


def importable(before: Item, after: Item, *, has_bookmarks: bool) -> tuple[Item | None, list[str]]:
    """What of a change a CSV row can carry: the item to write (None: nothing) and why not all.

    Unsupported parts are reverted to their old value, so the rest of the change still imports.
    """
    if after.kind is ItemKind.BOOKMARK or has_bookmarks:
        return None, [BOOKMARK_REASON]
    if any("," in value for name in _LISTS.values() for value in after.get(name)):
        return None, ["values containing a comma (the CSV import would split them)"]
    reasons = []
    if before.libraries != after.libraries:
        reasons.append("library membership (change it in forScore)")
    if after.key and after.key != before.key and keys.to_signature(after.key) is None:
        reasons.append(f"key {after.key} (too many sharps or flats for the CSV format)")
        after = replace(after, key=before.key)
    return after, reasons


def row(item: Item) -> dict[str, str]:
    start, _, end = (item.pages or "").partition("-")
    minutes, _, seconds = (item.duration or "").partition(":")
    signature = keys.to_signature(item.key) if item.key and "unknown" not in item.key else None
    return {
        "Filename": item.path or "",
        "Title": item.title,
        "Start Page (Bookmark)": start if item.kind is ItemKind.BOOKMARK else "",
        "End Page (Bookmark)": (end or start) if item.kind is ItemKind.BOOKMARK else "",
        **{column: ", ".join(item.get(name)) for column, name in _LISTS.items()},
        "Reference": item.reference or "",
        "Rating": str(item.rating or 0),
        "Difficulty": str(item.difficulty or 0),
        "Minutes": str(int(minutes)) if minutes else "",
        "Seconds": str(int(seconds)) if seconds else "",
        "keysf": str(signature[0]) if signature else "",
        "keymi": str(signature[1]) if signature else "",
    }


def create(directory: Path, before: list[Item], expected: list[Item]) -> PendingImport:
    stamp = datetime.now()
    import_id = stamp.strftime("%Y%m%d-%H%M%S-%f")
    folder = directory / import_id
    folder.mkdir(parents=True)
    # the file name is what the user picks in forScore's import list
    path = folder / f"forscore-mcp {stamp:%Y-%m-%d %H.%M.%S}.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(row(item) for item in expected)
    pending = PendingImport(import_id, path, before, expected)
    pending.save()
    return pending


def deliver(path: Path) -> bool:
    """Hand the CSV to forScore (it copies it into its import list). False if not possible."""
    if sys.platform != "darwin" or shutil.which("open") is None:
        return False
    result = subprocess.run(["open", "-a", "forScore", str(path)], capture_output=True)
    return result.returncode == 0


def differences(wanted: list[Item], current: dict[str, Item]) -> list[Mismatch]:
    """CSV-carried fields where the library differs from ``wanted`` (matched by UUID)."""
    found = []
    for item in wanted:
        actual = current.get(item.uuid)
        if actual is None:
            found.append(Mismatch(item.name, "item", "present", None))
            continue
        found += [
            Mismatch(item.name, name, item.get(name), actual.get(name))
            for name in CSV_FIELDS
            if _comparable(name, item) != _comparable(name, actual)
        ]
    return found


def _comparable(name: str, item: Item) -> Any:
    value = item.get(name)
    if name == "key" and value:
        signature = keys.to_signature(value)  # enharmonic spellings import as either
        return signature or value
    if isinstance(value, list):
        return sorted(value)
    return value
