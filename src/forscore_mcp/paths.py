"""Filesystem locations. Each can be overridden with an environment variable."""

import os
from pathlib import Path

DEFAULT_LIBRARY = (
    Path.home()
    / "Library/Containers/com.mgsdevelopment.forscore/Data/Library/Preferences/library.4sl"
)
DEFAULT_STATE_DIR = Path.home() / "Library/Application Support/forscore-mcp"
DEFAULT_BACKUP_DIR = DEFAULT_STATE_DIR / "backups"


def library_path() -> Path:
    return Path(os.environ.get("FORSCORE_LIBRARY", DEFAULT_LIBRARY)).expanduser()


def backup_dir() -> Path:
    return Path(os.environ.get("FORSCORE_BACKUP_DIR", DEFAULT_BACKUP_DIR)).expanduser()


def state_dir() -> Path:
    return Path(os.environ.get("FORSCORE_STATE_DIR", DEFAULT_STATE_DIR)).expanduser()


def imports_dir() -> Path:
    """Where generated import CSVs and their expected results are kept."""
    return state_dir() / "imports"


def config_file() -> Path:
    return state_dir() / "config.json"


def documents_dir(library: Path) -> Path:
    """forScore keeps PDFs in Data/Documents; the library is in Data/Library/Preferences."""
    return library.parent.parent.parent / "Documents"
