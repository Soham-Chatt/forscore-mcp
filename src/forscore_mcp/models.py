"""Plain data types shared by the library, CLI and MCP server."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class MetaKind(StrEnum):
    """Multi-valued categories. Values double as changeset/CLI keys."""

    COMPOSERS = "composers"
    GENRES = "genres"
    TAGS = "tags"
    LABELS = "labels"
    LIBRARIES = "libraries"  # existing libraries only; created and renamed in forScore


class ItemKind(StrEnum):
    SCORE = "score"
    BOOKMARK = "bookmark"


# Single-valued fields a changeset may set directly.
SCALAR_FIELDS = ("title", "reference", "key", "rating", "difficulty", "duration")
LIST_FIELDS = tuple(kind.value for kind in MetaKind)
FIELDS = (*SCALAR_FIELDS, *LIST_FIELDS)
MAX_RATING, MAX_DIFFICULTY = 5, 3
_DURATION = re.compile(r"^(\d+):([0-5]\d)$")


@dataclass(frozen=True)
class Item:
    """A score, or a bookmark (a page range within a score) with its own metadata."""

    uuid: str
    title: str
    kind: ItemKind = ItemKind.SCORE
    parent: str | None = None  # bookmarks: the score's title
    pages: str | None = None  # bookmarks: "7" or "7-9"
    reference: str | None = None
    key: str | None = None
    rating: int | None = None
    difficulty: int | None = None
    duration: str | None = None  # "m:ss"
    composers: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    libraries: list[str] = field(default_factory=list)
    path: str | None = None  # PDF file name (a bookmark shares its score's)

    @property
    def name(self) -> str:
        """Unique, readable label: "Kinderszenen" or "Kinderszenen › Träumerei"."""
        return f"{self.parent} › {self.title}" if self.parent else self.title

    def get(self, name: str) -> Any:
        return getattr(self, name)

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        data = {"name": self.name, **asdict(self)}
        if compact:  # drop empty fields and the redundant ones: much smaller for LLM context
            data = {k: v for k, v in data.items() if v not in (None, [], "") and k != "title"}
            if self.kind is ItemKind.SCORE:
                data.pop("kind")
        return data


@dataclass(frozen=True)
class MetaValue:
    value: str
    count: int
    sort_name: str | None = None  # composers only

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class Setlist:
    title: str
    uuid: str
    items: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_duration(value: str) -> tuple[int, int]:
    match = _DURATION.match(value.strip())
    if not match:
        raise ValueError(f"Duration must look like 3:05, not {value!r}.")
    return int(match[1]), int(match[2])


def format_duration(minutes: int | None, seconds: int | None) -> str | None:
    if not minutes and not seconds:
        return None
    return f"{minutes or 0}:{seconds or 0:02d}"
