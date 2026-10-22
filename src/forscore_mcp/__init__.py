"""forScore library tooling: Python API, CLI and MCP server."""

from importlib.metadata import version
from importlib.resources import files

__version__ = version("forscore-mcp")


def conventions() -> str:
    """The metadata conventions guide shipped with the package (single source of truth)."""
    return files(__package__).joinpath("conventions.md").read_text(encoding="utf-8")
