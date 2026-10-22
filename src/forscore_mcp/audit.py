"""Read-only library health checks: likely duplicates, file names, composer sort names."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .models import Item, ItemKind, MetaValue

# Particles whose sorting convention varies (de Falla → "Falla"? "de Falla"?): worth a check.
_PARTICLES = {"de", "di", "da", "del", "della", "du", "le", "la", "d'", "dal", "ten", "ter"}
_ARTICLES = ("the ", "a ", "an ")
_SOURCE_SUFFIX = re.compile(r"\s+-\s+(mn|ms)\d+$", re.IGNORECASE)  # e.g. "- MN0091409"


@dataclass
class AuditReport:
    duplicate_titles: list[list[str]] = field(default_factory=list)
    identical_files: list[list[str]] = field(default_factory=list)
    filename_mismatches: list[dict[str, str]] = field(default_factory=list)
    sort_names: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalise(text: str) -> str:
    """Compare titles loosely: no accents, case, punctuation or extra spaces."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s]|_", " ", text.casefold())
    return " ".join(text.split())


def run(items: list[Item], composers: list[MetaValue], documents: Path) -> AuditReport:
    scores = [i for i in items if i.kind is ItemKind.SCORE]
    return AuditReport(
        duplicate_titles=_groups((normalise(s.title), s.name) for s in scores),
        identical_files=_groups(
            (digest, s.name) for s in scores if (digest := _digest(documents, s.path))
        ),
        filename_mismatches=[
            {"item": s.name, "file": s.path}
            for s in scores
            if s.path and normalise(_stem(s.path)) != normalise(s.title)
        ],
        sort_names=[
            {"composer": c.value, "sort_name": c.sort_name or "", "reason": reason}
            for c in composers
            if (reason := _sort_name_issue(c.value, c.sort_name))
        ],
    )


def _groups(pairs: Any) -> list[list[str]]:
    groups: dict[Any, list[str]] = defaultdict(list)
    for key, name in pairs:
        groups[key].append(name)
    return sorted(names for names in groups.values() if len(names) > 1)


def _digest(documents: Path, file: str | None) -> str | None:
    path = documents / file if file else None
    if path is None or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stem(file: str) -> str:
    return _SOURCE_SUFFIX.sub("", Path(file).stem)


def _sort_name_issue(name: str, sort_name: str | None) -> str | None:
    if not sort_name:
        return "no sort name"
    lowered = name.casefold()
    if lowered.startswith(_ARTICLES):
        return "starts with an article; sort without it"
    if not lowered.endswith(sort_name.casefold()):
        return "sort name is not the end of the name"
    words = name.split()
    if len(words) >= 3 and sort_name == words[-1] and words[-2].casefold() in _PARTICLES:
        return f"check whether '{words[-2]}' belongs in the sort name"
    return None
