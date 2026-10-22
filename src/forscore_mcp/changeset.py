"""Declarative changesets: parse, run against a Store, report what changed.

A changeset is JSON (see examples/changeset.example.json)::

    {
      "renames": {"composers": {"Chopin": "Frédéric Chopin"}},
      "scores": [
        {"match": "Waltz in B Minor",                 # UUID or exact title
         "set": {"title": "Waltz in B minor", "reference": "Op. 69 No. 2",
                 "key": "B minor", "genres": ["Romantic"]},
         "add": {"tags": ["ABRSM Grade 5"]},
         "remove": {"tags": ["Old tag"]}}
      ],
      "prune": true                                   # delete values left unused (default)
    }

Renames run first, so score entries may already use the new names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import ChangesetError
from .models import SCALAR_FIELDS, MetaKind, Score
from .repository import Store

_KINDS = {kind.value: kind for kind in MetaKind}
_SET_FIELDS = (*SCALAR_FIELDS, *_KINDS)


@dataclass(frozen=True)
class ScoreChange:
    match: str
    set: dict[str, Any] = field(default_factory=dict)
    add: dict[MetaKind, list[str]] = field(default_factory=dict)
    remove: dict[MetaKind, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Changeset:
    renames: dict[MetaKind, dict[str, str]] = field(default_factory=dict)
    scores: list[ScoreChange] = field(default_factory=list)
    prune: bool = True


@dataclass
class Report:
    """Outcome of running a changeset. ``changes`` maps score title -> field -> [before, after]."""

    dry_run: bool
    changes: dict[str, dict[str, list[Any]]] = field(default_factory=dict)
    renamed: dict[str, dict[str, str]] = field(default_factory=dict)
    pruned: dict[str, list[str]] = field(default_factory=dict)
    backup: str | None = None

    @property
    def empty(self) -> bool:
        return not (self.changes or self.renamed or self.pruned)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "scores_changed": len(self.changes),
            "changes": self.changes,
            "renamed": self.renamed,
            "pruned": self.pruned,
            "backup": self.backup,
        }


def parse(data: Any) -> Changeset:
    if not isinstance(data, dict):
        raise ChangesetError("A changeset must be a JSON object.")
    _only(data, {"renames", "scores", "prune"}, "changeset")
    renames = {
        _kind(name): _str_map(mapping, f"renames.{name}")
        for name, mapping in _dict(data.get("renames", {}), "renames").items()
    }
    scores = [_parse_score(entry, i) for i, entry in enumerate(_list(data.get("scores", [])))]
    prune = data.get("prune", True)
    if not isinstance(prune, bool):
        raise ChangesetError("'prune' must be true or false.")
    return Changeset(renames, scores, prune)


def run(store: Store, changeset: Changeset, *, dry_run: bool) -> Report:
    """Apply ``changeset`` to ``store`` (caller owns the transaction) and report the diff."""
    before = {pk: s for pk, s in zip(store.score_pks(), store.scores(), strict=True)}
    report = Report(dry_run=dry_run)
    touched: set[int] = set()

    for kind, mapping in changeset.renames.items():
        for old, new in mapping.items():
            items = store.rename(kind, old, new)
            if items is not None:
                touched |= items
                report.renamed.setdefault(kind.value, {})[old] = new

    for change in changeset.scores:
        pk = store.find(change.match)
        for name, value in change.set.items():
            if name in _KINDS:
                store.set_values(pk, _KINDS[name], value)
            else:
                store.set_scalar(pk, name, value)
        for kind, values in change.add.items():
            store.add_values(pk, kind, values)
        for kind, values in change.remove.items():
            store.remove_values(pk, kind, values)
        touched.add(pk)

    if changeset.prune:
        for kind in MetaKind:
            if removed := store.prune(kind):
                report.pruned[kind.value] = removed

    after = dict(zip(touched, store.scores(touched), strict=True))
    for pk in sorted(touched):
        diff = _diff(before[pk], after[pk])
        if diff:
            report.changes[after[pk].title] = diff
    store.touch(pk for pk in touched if after[pk] != before[pk])
    return report


def _diff(before: Score, after: Score) -> dict[str, list[Any]]:
    fields = (*SCALAR_FIELDS, *_KINDS)
    return {
        name: [before.get(name), after.get(name)]
        for name in fields
        if before.get(name) != after.get(name)
    }


def _parse_score(entry: Any, index: int) -> ScoreChange:
    where = f"scores[{index}]"
    entry = _dict(entry, where)
    _only(entry, {"match", "set", "add", "remove"}, where)
    match = entry.get("match")
    if not isinstance(match, str) or not match:
        raise ChangesetError(f"{where}.match must be a UUID or title.")
    updates = _dict(entry.get("set", {}), f"{where}.set")
    _only(updates, set(_SET_FIELDS), f"{where}.set")
    for name, value in updates.items():
        if name in _KINDS:
            updates[name] = _str_list(value, f"{where}.set.{name}")
        elif value is not None and not isinstance(value, str):
            raise ChangesetError(f"{where}.set.{name} must be text or null.")
    return ScoreChange(
        match=match,
        set=updates,
        add=_kind_lists(entry.get("add", {}), f"{where}.add"),
        remove=_kind_lists(entry.get("remove", {}), f"{where}.remove"),
    )


def _kind_lists(value: Any, where: str) -> dict[MetaKind, list[str]]:
    return {
        _kind(name): _str_list(items, f"{where}.{name}")
        for name, items in _dict(value, where).items()
    }


def _kind(name: str) -> MetaKind:
    if name not in _KINDS:
        raise ChangesetError(f"Unknown category {name!r}; use one of {sorted(_KINDS)}.")
    return _KINDS[name]


def _only(data: dict[str, Any], allowed: set[str], where: str) -> None:
    if unknown := set(data) - allowed:
        raise ChangesetError(f"Unknown keys in {where}: {sorted(unknown)}.")


def _dict(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ChangesetError(f"{where} must be an object.")
    return dict(value)


def _list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ChangesetError("'scores' must be a list.")
    return value


def _str_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ChangesetError(f"{where} must be a list of non-empty strings.")
    return value


def _str_map(value: Any, where: str) -> dict[str, str]:
    mapping = _dict(value, where)
    if not all(isinstance(v, str) and v.strip() for v in mapping.values()):
        raise ChangesetError(f"{where} values must be non-empty strings.")
    return mapping
