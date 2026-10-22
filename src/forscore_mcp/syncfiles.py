"""forScore's per-score sync files.

forScore syncs metadata between devices through one ``<pdf name>.itm`` file per score in
``Preferences/Sync`` (a gzipped binary plist), not through the database. The app rewrites a
score's file whenever it is edited in the app and notices changed files by size and mtime
(``.syncFolderState``). Edits made directly in the database must therefore also be written
here, or other devices never see them. Bookmarks live inside their score's file, under
``bookmarks``, with capitalised keys and matched by ``Identifier`` (the bookmark's UUID).
See docs/schema.md.
"""

from __future__ import annotations

import gzip
import plistlib
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import keys
from .models import Item, ItemKind, parse_duration

SUFFIX = ".itm"
_SEPARATOR = ", "


def _join(values: list[str]) -> str | None:
    return _SEPARATOR.join(values) or None


def _key(item: Item) -> int | None:
    return keys.encode(item.key) if item.key and not item.key.startswith("unknown") else None


def _duration_part(index: int) -> Callable[[Item], int | None]:
    return lambda item: parse_duration(item.duration)[index] if item.duration else None


# Item -> sync-file value, per key. None or "" removes the key, as forScore does.
_Getter = Callable[[Item], Any]
_COMMON: dict[str, _Getter] = {
    "title": lambda i: i.title,
    "composer": lambda i: _join(i.composers),
    "genre": lambda i: _join(i.genres),
    "reference": lambda i: i.reference,
    "key": _key,
    "rating": lambda i: i.rating,
    "difficulty": lambda i: i.difficulty,
    "minutes": _duration_part(0),
    "seconds": _duration_part(1),
}
SCORE_FIELDS: dict[str, _Getter] = {
    **_COMMON,
    "keywords": lambda i: _join(i.tags),
    "labels": lambda i: _join(i.labels),
    "libraries": lambda i: _join(i.libraries),
}
BOOKMARK_FIELDS: dict[str, _Getter] = {
    **{name.capitalize(): get for name, get in _COMMON.items()},
    "Keyword": lambda i: _join(i.tags),
    "Label": lambda i: _join(i.labels),
}
_LIST_FIELDS = {"composer", "genre", "keywords", "labels", "libraries", "keyword", "label"}


@dataclass(frozen=True)
class Drift:
    item: str
    field: str
    sync_file: Any
    library: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sync_dir(library_path: Path) -> Path:
    return library_path.parent / "Sync"


def path_for(directory: Path, item: Item) -> Path | None:
    return directory / f"{item.path}{SUFFIX}" if item.path else None


def read(path: Path) -> dict[str, Any]:
    return plistlib.loads(gzip.decompress(path.read_bytes()))


def write(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(gzip.compress(plistlib.dumps(data, fmt=plistlib.FMT_BINARY)))
    tmp.replace(path)


def update(directory: Path, item: Item) -> bool:
    """Write ``item``'s metadata into its sync file, keeping all other keys.

    Returns False if there is nothing to update yet (forScore creates the file or bookmark
    entry itself later).
    """
    path = path_for(directory, item)
    if path is None or not path.exists():
        return False
    data = read(path)
    entry, fields = _entry(data, item)
    if entry is None:
        return False
    for name, get in fields.items():
        value = get(item)
        if value in (None, ""):
            entry.pop(name, None)
        else:
            entry[name] = value
    write(path, data)
    return True


def drift(directory: Path, items: list[Item]) -> list[Drift]:
    """Fields where an item's sync file disagrees with the library (what other devices see)."""
    found = []
    cache: dict[Path, dict[str, Any]] = {}
    for item in items:
        path = path_for(directory, item)
        if path is None or not path.exists():
            continue
        if path not in cache:
            cache[path] = read(path)
        entry, fields = _entry(cache[path], item)
        if entry is None:
            found.append(Drift(item.name, "bookmark", None, item.title))
            continue
        for name, get in fields.items():
            expected, actual = get(item), entry.get(name)
            if _normalise(name, actual) != _normalise(name, expected):
                found.append(Drift(item.name, name, actual, expected))
    return found


def copy_dir(source: Path, target: Path) -> None:
    """Copy the sync files (not forScore's hidden state files) for a backup or restore."""
    target.mkdir(parents=True, exist_ok=True)
    for file in source.glob(f"*{SUFFIX}"):
        shutil.copy2(file, target / file.name)


def _entry(data: dict[str, Any], item: Item) -> tuple[dict[str, Any] | None, dict[str, _Getter]]:
    if item.kind is ItemKind.SCORE:
        return data, SCORE_FIELDS
    for bookmark in data.get("bookmarks", []):
        if isinstance(bookmark, dict) and bookmark.get("Identifier") == item.uuid:
            return bookmark, BOOKMARK_FIELDS
    return None, BOOKMARK_FIELDS


def _normalise(name: str, value: Any) -> Any:
    if value in (None, "", 0):
        return None
    if name.lower() in _LIST_FIELDS:  # forScore may reorder list values
        return frozenset(v.strip() for v in str(value).split(","))
    return value
