"""Filesystem locations. Each can be overridden with an environment variable."""

import os
from pathlib import Path

DEFAULT_LIBRARY = (
    Path.home()
    / "Library/Containers/com.mgsdevelopment.forscore/Data/Library/Preferences/library.4sl"
)
DEFAULT_BACKUP_DIR = Path.home() / "Library/Application Support/forscore-mcp/backups"


def library_path() -> Path:
    return Path(os.environ.get("FORSCORE_LIBRARY", DEFAULT_LIBRARY)).expanduser()


def backup_dir() -> Path:
    return Path(os.environ.get("FORSCORE_BACKUP_DIR", DEFAULT_BACKUP_DIR)).expanduser()


def documents_dir(library: Path) -> Path:
    """forScore keeps PDFs in Data/Documents; the library is in Data/Library/Preferences."""
    return library.parent.parent.parent / "Documents"
