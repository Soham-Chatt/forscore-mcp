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
from .library import Library
from .models import MetaKind

INSTRUCTIONS = """\
Tools to read and fix metadata (title, composer, reference, key, genre, tags, labels) in the
user's forScore sheet-music library on macOS. Read `get_conventions` before proposing changes.
Never apply a changeset the user has not approved; always preview first, and ask the user to
quit forScore on the Mac before `apply_changeset`."""

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
            except ForScoreError as exc:
                raise ToolError(str(exc)) from exc

        return server.tool(annotations=annotations)(wrapper)

    return decorate


@_tool(READ)
def list_scores(query: str | None = None) -> list[dict[str, Any]]:
    """List all scores with their metadata, optionally filtered by a case-insensitive search
    over title, reference, composers, genres and tags."""
    return [s.to_dict() for s in Library().scores(query)]


@_tool(READ)
def get_score(match: str) -> dict[str, Any]:
    """Get one score by UUID or exact (case-insensitive) title."""
    return Library().score(match).to_dict()


@_tool(READ)
def list_values(kind: MetaKind) -> list[dict[str, Any]]:
    """List every composer, genre, tag or label value in use, with how many scores use it."""
    return [v.to_dict() for v in Library().values(kind)]


@_tool(READ)
def preview_changeset(changeset: dict[str, Any]) -> dict[str, Any]:
    """Dry-run a changeset on a copy of the library and return the per-score diff.
    Format: {"renames": {"composers": {"Old": "New"}}, "scores": [{"match": "<uuid or title>",
    "set": {"title", "reference", "key", "composers", "genres", "tags", "labels"},
    "add": {"tags": [...]}, "remove": {...}}], "prune": true}. Safe while forScore is open."""
    return Library().preview(changeset).to_dict()


@_tool(WRITE)
def apply_changeset(changeset: dict[str, Any], confirm: bool = False) -> dict[str, Any]:
    """Apply a changeset to the live library (backup first, single transaction).
    Requires forScore to be quit on the Mac. Without confirm=true this only previews."""
    library = Library()
    report = library.apply(changeset) if confirm else library.preview(changeset)
    return report.to_dict()


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
    Requires forScore to be quit and confirm=true."""
    if not confirm:
        raise ToolError("Restoring overwrites the library; call again with confirm=true.")
    return {"restored": backup_id, "previous_state_backup": Library().restore(backup_id).id}


@_tool(READ)
def convert_key(value: str) -> dict[str, Any]:
    """Convert between a key name ("E♭ major") and forScore's stored code (300)."""
    try:
        code = int(value) if value.strip().isdigit() else keys.encode(value)
        return {"name": keys.decode(code), "code": code}
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@_tool(READ)
def doctor() -> list[dict[str, object]]:
    """Check that the library is reachable and whether changes can be applied right now."""
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
