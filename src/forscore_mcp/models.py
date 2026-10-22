"""Plain data types shared by the library, CLI and MCP server."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class MetaKind(StrEnum):
    """Multi-valued metadata categories. Values double as changeset/CLI keys."""

    COMPOSERS = "composers"
    GENRES = "genres"
    TAGS = "tags"
    LABELS = "labels"


# Single-valued fields a changeset may set directly on a score.
SCALAR_FIELDS = ("title", "reference", "key")


@dataclass(frozen=True)
class Score:
    uuid: str
    title: str
    reference: str | None = None
    key: str | None = None
    composers: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def get(self, name: str) -> Any:
        return getattr(self, name)


@dataclass(frozen=True)
class MetaValue:
    value: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
