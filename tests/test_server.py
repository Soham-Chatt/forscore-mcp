import asyncio
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from forscore_mcp.server import server

pytestmark = pytest.mark.usefixtures("library")


def call(name: str, **arguments: Any) -> Any:
    result = asyncio.run(server.call_tool(name, arguments))
    assert not getattr(result, "is_error", False), result
    return result.structured_content  # ty: ignore[unresolved-attribute]


def test_tools_registered() -> None:
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"list_scores", "preview_changeset", "apply_changeset", "get_conventions"} <= names


def test_read_tools() -> None:
    assert call("list_scores")["total"] == 5
    assert call("get_score", match="Wet Hands")["key"] == "A major"
    assert call("convert_key", value="A minor") == {"name": "A minor", "code": 611}


def test_apply_requires_confirm() -> None:
    changes = {"scores": [{"match": "Wet Hands", "set": {"key": "A minor"}}]}
    assert call("apply_changeset", changeset=changes)["dry_run"] is True
    report = call("apply_changeset", changeset=changes, confirm=True)
    assert report["method"] == "csv"
    assert call("verify_import", import_id=report["import_id"])["status"] == "not imported yet"
    direct = call("apply_changeset", changeset=changes, confirm=True, method="direct")
    assert direct["dry_run"] is False  # this module's fixture enables the danger zone
    assert call("get_score", match="Wet Hands")["key"] == "A minor"
    assert call("verify_import", import_id=report["import_id"])["status"] == "imported"


def test_library_errors_become_tool_errors() -> None:
    with pytest.raises(ToolError, match="No score"):
        asyncio.run(server.call_tool("get_score", {"match": "Nope"}))
