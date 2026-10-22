"""forScore's per-score sync files.

forScore syncs metadata between devices through one ``<pdf name>.itm`` file per score in
``Preferences/Sync`` (a gzipped binary plist), not through the database. The app rewrites a
score's file whenever the score is edited in the app; edits made directly in the database must
therefore also be written here, or other devices never see them. See docs/schema.md.
"""

from __future__ import annotations

import gzip
import plistlib
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import keys
from .models import Score

SUFFIX = ".itm"
_SEPARATOR = ", "
# sync-file key -> how to derive it from a Score; None/empty removes the key, as forScore does
_FIELDS = {
    "title": lambda s: s.title,
    "composer": lambda s: _join(s.composers),
    "genre": lambda s: _join(s.genres),
    "keywords": lambda s: _join(s.tags),
    "labels": lambda s: _join(s.labels),
    "reference": lambda s: s.reference,
    "key": lambda s: keys.encode(s.key) if s.key and not s.key.startswith("unknown") else None,
}
_LIST_FIELDS = {"composer", "genre", "keywords", "labels"}


@dataclass(frozen=True)
class Drift:
    score: str
    field: str
    sync_file: Any
    library: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sync_dir(library_path: Path) -> Path:
    return library_path.parent / "Sync"


def path_for(directory: Path, score: Score) -> Path | None:
    return directory / f"{score.path}{SUFFIX}" if score.path else None


def read(path: Path) -> dict[str, Any]:
    return plistlib.loads(gzip.decompress(path.read_bytes()))


def write(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(gzip.compress(plistlib.dumps(data, fmt=plistlib.FMT_BINARY)))
    tmp.replace(path)


def update(directory: Path, score: Score) -> bool:
    """Write ``score``'s metadata into its sync file, keeping all other keys.

    Returns False if the score has no sync file yet (forScore creates it later).
    """
    path = path_for(directory, score)
    if path is None or not path.exists():
        return False
    data = read(path)
    for name, derive in _FIELDS.items():
        value = derive(score)
        if value in (None, ""):
            data.pop(name, None)
        else:
            data[name] = value
    write(path, data)
    return True


def drift(directory: Path, scores: list[Score]) -> list[Drift]:
    """Fields where a score's sync file disagrees with the library (what other devices see)."""
    found = []
    for score in scores:
        path = path_for(directory, score)
        if path is None or not path.exists():
            continue
        data = read(path)
        for name, derive in _FIELDS.items():
            expected, actual = derive(score), data.get(name)
            if _normalise(name, actual) != _normalise(name, expected):
                found.append(Drift(score.title, name, actual, expected))
    return found


def copy_dir(source: Path, target: Path) -> None:
    """Copy the sync files (not forScore's hidden state files) for a backup or restore."""
    target.mkdir(parents=True, exist_ok=True)
    for file in source.glob(f"*{SUFFIX}"):
        shutil.copy2(file, target / file.name)


def _join(values: list[str]) -> str | None:
    return _SEPARATOR.join(values) or None


def _normalise(name: str, value: Any) -> Any:
    if value in (None, ""):
        return None
    if name in _LIST_FIELDS:  # forScore may reorder list values
        return frozenset(v.strip() for v in str(value).split(","))
    return value
