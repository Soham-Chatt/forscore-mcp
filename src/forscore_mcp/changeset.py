"""Declarative changesets: parse, run against a Store, report what changed.

A changeset is JSON (see examples/changeset.example.json)::

    {
      "renames": {"composers": {"Chopin": "Frédéric Chopin"}},
      "sort_names": {"Ralph Vaughan Williams": "Vaughan Williams"},
      "items": [
        {"match": "Waltz in B Minor",            # UUID, exact title, or "Score › Bookmark"
         "set": {"title": "Waltz in B minor", "reference": "Op. 69 No. 2", "key": "B minor",
                 "rating": 4, "difficulty": 2, "duration": "2:45", "genres": ["Romantic"]},
         "add": {"tags": ["ABRSM Grade 5"], "libraries": ["Personal"]},
         "remove": {"tags": ["Old tag"]}}
      ],
      "prune": true                              # delete values left unused (default)
    }

"scores" is accepted as an alias of "items". Renames and sort names run first, so item entries
may already use the new names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import ChangesetError
from .models import FIELDS, MAX_DIFFICULTY, MAX_RATING, SCALAR_FIELDS, Item, MetaKind
from .repository import Store

_KINDS = {kind.value: kind for kind in MetaKind}
_INT_FIELDS = {"rating": MAX_RATING, "difficulty": MAX_DIFFICULTY}


@dataclass(frozen=True)
class ItemChange:
    match: str
    set: dict[str, Any] = field(default_factory=dict)
    add: dict[MetaKind, list[str]] = field(default_factory=dict)
    remove: dict[MetaKind, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Changeset:
    renames: dict[MetaKind, dict[str, str]] = field(default_factory=dict)
    sort_names: dict[str, str] = field(default_factory=dict)
    items: list[ItemChange] = field(default_factory=list)
    prune: bool = True


@dataclass
class Report:
    """Outcome of running a changeset. ``changes`` maps item name -> field -> [before, after]."""

    dry_run: bool
    changes: dict[str, dict[str, list[Any]]] = field(default_factory=dict)
    renamed: dict[str, dict[str, str]] = field(default_factory=dict)
    sort_names: dict[str, str] = field(default_factory=dict)
    pruned: dict[str, list[str]] = field(default_factory=dict)
    backup: str | None = None
    sync_files_updated: int = 0
    updated: list[Item] = field(default_factory=list, repr=False)  # after-state, not serialised

    @property
    def empty(self) -> bool:
        return not (self.changes or self.renamed or self.sort_names or self.pruned)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "items_changed": len(self.changes),
            "changes": self.changes,
            "renamed": self.renamed,
            "sort_names": self.sort_names,
            "pruned": self.pruned,
            "backup": self.backup,
            "sync_files_updated": self.sync_files_updated,
        }


def parse(data: Any) -> Changeset:
    if not isinstance(data, dict):
        raise ChangesetError("A changeset must be a JSON object.")
    _only(data, {"renames", "sort_names", "items", "scores", "prune"}, "changeset")
    if "items" in data and "scores" in data:
        raise ChangesetError("Use either 'items' or 'scores', not both.")
    renames = {
        _kind(name): _str_map(mapping, f"renames.{name}")
        for name, mapping in _dict(data.get("renames", {}), "renames").items()
    }
    entries = data.get("items", data.get("scores", []))
    if not isinstance(entries, list):
        raise ChangesetError("'items' must be a list.")
    prune = data.get("prune", True)
    if not isinstance(prune, bool):
        raise ChangesetError("'prune' must be true or false.")
    return Changeset(
        renames=renames,
        sort_names=_str_map(data.get("sort_names", {}), "sort_names"),
        items=[_parse_item(entry, i) for i, entry in enumerate(entries)],
        prune=prune,
    )


def run(store: Store, changeset: Changeset, *, dry_run: bool) -> Report:
    """Apply ``changeset`` to ``store`` (caller owns the transaction) and report the diff."""
    before = dict(zip(store.item_pks(), store.items(), strict=True))
    report = Report(dry_run=dry_run)
    touched: set[int] = set()

    for kind, mapping in changeset.renames.items():
        for old, new in mapping.items():
            items = store.rename(kind, old, new)
            if items is not None:
                touched |= items
                report.renamed.setdefault(kind.value, {})[old] = new
    for composer, sort_name in changeset.sort_names.items():
        if store.set_sort_name(composer, sort_name):
            report.sort_names[composer] = sort_name

    for change in changeset.items:
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
        if MetaKind.LIBRARIES in (*change.add, *change.remove) or "libraries" in change.set:
            touched.update(store.bookmark_pks(pk))

    if changeset.prune:
        for kind in MetaKind:
            if removed := store.prune(kind):
                report.pruned[kind.value] = removed

    after = dict(zip(touched, store.items(touched), strict=True))
    changed = [pk for pk in store.item_pks() if pk in touched and after[pk] != before[pk]]
    for pk in changed:
        report.changes[after[pk].name] = _diff(before[pk], after[pk])
    store.touch(changed)
    report.updated = [after[pk] for pk in changed]
    return report


def _diff(before: Item, after: Item) -> dict[str, list[Any]]:
    return {
        name: [before.get(name), after.get(name)]
        for name in FIELDS
        if before.get(name) != after.get(name)
    }


def _parse_item(entry: Any, index: int) -> ItemChange:
    where = f"items[{index}]"
    entry = _dict(entry, where)
    _only(entry, {"match", "set", "add", "remove"}, where)
    match = entry.get("match")
    if not isinstance(match, str) or not match:
        raise ChangesetError(f"{where}.match must be a UUID or title.")
    updates = _dict(entry.get("set", {}), f"{where}.set")
    _only(updates, set(FIELDS), f"{where}.set")
    for name, value in updates.items():
        here = f"{where}.set.{name}"
        if name in _KINDS:
            updates[name] = _str_list(value, here)
        elif name in _INT_FIELDS:
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool)
                or not 0 <= value <= _INT_FIELDS[name]
            ):  # fmt: skip
                raise ChangesetError(f"{here} must be 0-{_INT_FIELDS[name]} or null.")
        elif name in SCALAR_FIELDS and value is not None and not isinstance(value, str):
            raise ChangesetError(f"{here} must be text or null.")
    return ItemChange(
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


def _str_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ChangesetError(f"{where} must be a list of non-empty strings.")
    return value


def _str_map(value: Any, where: str) -> dict[str, str]:
    mapping = _dict(value, where)
    if not all(isinstance(v, str) and v.strip() for v in mapping.values()):
        raise ChangesetError(f"{where} values must be non-empty strings.")
    return mapping
