"""The version must match across the package, plugin manifests and the plugin's MCP pin."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def test_versions_in_sync() -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert load("plugin/.claude-plugin/plugin.json")["version"] == version
    assert load(".claude-plugin/marketplace.json")["plugins"][0]["version"] == version
    args = load("plugin/.mcp.json")["mcpServers"]["forscore"]["args"]
    assert any(arg.endswith(f"@v{version}") for arg in args)
