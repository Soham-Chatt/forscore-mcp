"""MCP server (stdio). Thin wrapper over `Library`; every tool maps to one library call."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__, conventions, keys
from .doctor import run_checks
from .errors import ForScoreError
from .library import Filters, Library, WriteMethod
from .models import ItemKind, MetaKind

INSTRUCTIONS = """\
Tools to read and fix metadata (title, composer, reference, key, rating, difficulty, duration,
genre, tags, labels) of scores and bookmarks in the user's forScore sheet-music library on
macOS. Read `get_conventions` before proposing changes. Never apply a changeset the user has not
approved; always preview first. Changes are written as a CSV the user imports in forScore
(Backups › Metadata › Import); afterwards call `verify_import`."""

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)

server = MCPServer("forscore", version=__version__, instructions=INSTRUCTIONS)


def _tool(annotations: ToolAnnotations) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a tool; library errors become user-readable tool errors."""

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except (ForScoreError, ValueError) as exc:
                raise ToolError(str(exc)) from exc

        return server.tool(annotations=annotations)(wrapper)

    return decorate


@_tool(READ)
def list_scores(
    query: str | None = None,
    kind: ItemKind | None = None,
    composer: str | None = None,
    genre: str | None = None,
    tag: str | None = None,
    label: str | None = None,
    library: str | None = None,
    missing: str | None = None,
    offset: int = 0,
    limit: int = 50,
    full: bool = False,
) -> dict[str, Any]:
    """List scores and their bookmarks, a page at a time (see `total`; raise `offset` for more).
    Filters combine: `query` searches titles, references, composers, genres and tags;
    composer/genre/tag/label/library match a value exactly; `kind` is "score" or "bookmark";
    `missing` names a field that must be empty (e.g. "composers", "reference", "key").
    Items are compact (empty fields omitted) unless `full` is true."""
    filters = Filters(query, kind, composer, genre, tag, label, library, missing)
    page = Library().page(filters, offset=offset, limit=limit)
    return {
        "total": page.total,
        "offset": page.offset,
        "items": [item.to_dict(compact=not full) for item in page.items],
    }


@_tool(READ)
def get_score(match: str) -> dict[str, Any]:
    """Get one score or bookmark by UUID, exact title, or "Score › Bookmark"."""
    return Library().item(match).to_dict()


@_tool(READ)
def list_values(kind: MetaKind, include_unused: bool = False) -> list[dict[str, Any]]:
    """List every composer, genre, tag, label or library in use, with usage counts
    (and sort names for composers). Unused values are hidden, as in forScore."""
    return [v.to_dict() for v in Library().values(kind, include_unused=include_unused)]


@_tool(READ)
def list_setlists() -> list[dict[str, Any]]:
    """List setlists with their scores and bookmarks in order."""
    return [s.to_dict() for s in Library().setlists()]


@_tool(READ)
def audit_library() -> dict[str, Any]:
    """Find likely duplicate titles, identical PDFs, PDF file names that differ from titles
    (rename those in forScore: changing a title there can rename the file), and composer sort
    names worth checking."""
    return Library().audit().to_dict()


@_tool(READ)
def preview_changeset(changeset: dict[str, Any]) -> dict[str, Any]:
    """Dry-run a changeset on a copy of the library and return the per-item diff.
    Format: {"renames": {"composers": {"Old": "New"}}, "sort_names": {"Composer": "Sort"},
    "items": [{"match": "<uuid, title or 'Score › Bookmark'>", "set": {"title", "reference",
    "key", "rating" (0-5), "difficulty" (0-3), "duration" ("m:ss"), "composers", "genres",
    "tags", "labels", "libraries"}, "add": {"tags": [...]}, "remove": {...}}], "prune": true}.
    Safe while forScore is open."""
    return Library().preview(changeset).to_dict()


@_tool(WRITE)
def apply_changeset(
    changeset: dict[str, Any], confirm: bool = False, method: WriteMethod = "csv"
) -> dict[str, Any]:
    """Write an approved changeset. Without confirm=true this only previews.
    method "csv" (default, supported by forScore): creates an import CSV and sends it to
    forScore; tell the user the `next_step` (import it in Backups › Metadata, check forScore's
    preview, tap Save), then call `verify_import`. Changes CSV cannot carry are listed under
    `skipped`. method "direct" writes the database itself; it only works if the user enabled
    the danger zone, needs forScore quit, and should only be used for skipped changes such as
    library membership or composer sort names."""
    library = Library()
    report = library.apply(changeset, method=method) if confirm else library.preview(changeset)
    return report.to_dict()


@_tool(READ)
def verify_import(import_id: str) -> dict[str, Any]:
    """After the user imported a CSV: check field by field that forScore applied it."""
    return Library().verify_import(import_id)


@_tool(WRITE)
def undo_import(import_id: str, confirm: bool = False) -> dict[str, Any]:
    """Create (and send to forScore) a CSV that restores the items of an earlier import.
    The user imports it the same way. Requires confirm=true."""
    if not confirm:
        raise ToolError("Undo creates a new import for the user; call again with confirm=true.")
    return Library().undo_import(import_id)


@_tool(READ)
def check_sync() -> list[dict[str, Any]]:
    """List metadata that differs between the library and the sync files other devices
    (iPad, iPhone) receive. Empty means everything is in sync."""
    return [d.to_dict() for d in Library().sync_drift()]


@_tool(READ)
def list_backups() -> list[dict[str, str]]:
    """List library backups, newest first."""
    return [b.to_dict() for b in Library().backups()]


@_tool(READ)
def create_backup() -> dict[str, str]:
    """Back up the library now."""
    return Library().backup().to_dict()


@_tool(WRITE)
def restore_backup(backup_id: str, confirm: bool = False) -> dict[str, str]:
    """Replace the library with a backup (the current state is backed up first).
    Danger zone only; requires forScore to be quit and confirm=true. Prefer undo_import."""
    if not confirm:
        raise ToolError("Restoring overwrites the library; call again with confirm=true.")
    return {"restored": backup_id, "previous_state_backup": Library().restore(backup_id).id}


@_tool(READ)
def convert_key(value: str) -> dict[str, Any]:
    """Convert between a key name ("E♭ major") and forScore's stored code (300)."""
    code = int(value) if value.strip().isdigit() else keys.encode(value)
    return {"name": keys.decode(code), "code": code}


@_tool(READ)
def doctor() -> list[dict[str, object]]:
    """Check that the library is reachable, in sync, and whether changes can be applied now."""
    return [c.to_dict() for c in run_checks()]


@_tool(READ)
def get_conventions() -> str:
    """The metadata conventions and the safe editing workflow. Read before proposing changes."""
    return conventions()


@server.resource("forscore://conventions", mime_type="text/markdown")
def conventions_resource() -> str:
    """Metadata conventions and editing workflow."""
    return conventions()


def main() -> None:
    server.run("stdio")
