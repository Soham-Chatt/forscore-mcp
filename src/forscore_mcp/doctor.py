"""Environment checks with actionable fixes, shared by `forscore-mcp doctor` and the MCP tool."""

from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass

from .errors import ForScoreError
from .library import Library
from .safety import forscore_running


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_checks(library: Library | None = None) -> list[Check]:
    library = library or Library()
    checks = [
        Check(
            "macOS",
            sys.platform == "darwin",
            "OK" if sys.platform == "darwin" else "forScore's library is only reachable on a Mac.",
        )
    ]
    try:
        count = len(library.scores())
        checks.append(Check("library", True, f"{count} scores in {library.path}"))
    except ForScoreError as exc:
        checks.append(Check("library", False, str(exc)))
    try:
        drift = library.sync_drift()
        scores_off = sorted({d.score for d in drift})
        checks.append(
            Check(
                "sync files",
                not drift,
                "OK, other devices see the same metadata."
                if not drift
                else f"{len(scores_off)} scores differ from what syncs to other devices "
                f"(e.g. {', '.join(scores_off[:3])}). See docs/schema.md#sync to resync.",
            )
        )
    except (ForScoreError, OSError) as exc:
        checks.append(Check("sync files", False, f"Cannot read sync files: {exc}"))
    running = forscore_running()
    checks.append(
        Check(
            "forScore closed",
            not running,
            "Running: reading works, but quit it (Cmd-Q) before applying changes."
            if running
            else "OK, changes can be applied.",
        )
    )
    backup_parent = library.backup_dir
    while not backup_parent.exists() and backup_parent != backup_parent.parent:
        backup_parent = backup_parent.parent
    writable = os.access(backup_parent, os.W_OK)
    checks.append(
        Check(
            "backups",
            writable,
            f"Backups go to {library.backup_dir}"
            if writable
            else f"Cannot write to {library.backup_dir}; set FORSCORE_BACKUP_DIR.",
        )
    )
    return checks
