"""The version must match across the package, the plugin manifest, the plugin's MCP pin and
the MCP registry metadata."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def test_versions_in_sync() -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert load("plugin/.claude-plugin/plugin.json")["version"] == version
    # The docs say to set the version in plugin.json only, never also in the marketplace entry.
    assert "version" not in load(".claude-plugin/marketplace.json")["plugins"][0]
    args = load("plugin/.mcp.json")["mcpServers"]["forscore"]["args"]
    assert f"forscore-mcp@{version}" in args
    server = load("server.json")
    assert server["version"] == server["packages"][0]["version"] == version
    readme = (ROOT / "README.md").read_text()
    assert f"<!-- mcp-name: {server['name']} -->" in readme  # registry ownership check
