# Releasing

One version number, kept in four places (`tests/test_versions.py` fails if they drift):
`pyproject.toml`, `plugin/.claude-plugin/plugin.json`, the `forscore-mcp@X.Y.Z` pin in
`plugin/.mcp.json`, and both versions in `server.json` (MCP registry). The marketplace entry
carries no version; plugin users only receive an update when `plugin.json` changes.

1. On a branch, bump the version everywhere (`uv version --bump minor`, then the plugin files and
   `server.json`), and update anything user-facing. Merge through a PR.
2. Tag the merge commit on `main` and push it: `git tag -a v1.1.0 -m v1.1.0 && git push origin v1.1.0`.
3. `release.yml` then:
   - runs CI and checks that the tag matches the package version,
   - builds and creates a GitHub Release,
   - publishes to PyPI (trusted publishing, environment `pypi`),
   - publishes `server.json` to the official MCP registry (GitHub OIDC; the README carries the
     `mcp-name` line that proves ownership).
4. Plugin users get the update with `claude plugin update forscore@forscore-mcp`; `uvx` users get
   it on their next run.

Before tagging, check the plugin locally:
- `claude plugin validate --strict plugin` and `claude plugin validate --strict .` (CI runs both).
- `claude --plugin-dir plugin`, then `/mcp` should show `forscore` as connected.
- `claude --plugin-dir plugin plugin details forscore`: keep the always-on cost small (about
  120 tokens at v0.1.1). The skill's `description` is what every session pays for.

Later option: submit the plugin to Anthropic's directory (claude.ai/directory/manage). It only
works in Claude Code, since the server needs the Mac's local library.
