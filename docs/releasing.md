# Releasing

One version number, kept in three places (`tests/test_versions.py` fails if they drift):
`pyproject.toml`, `plugin/.claude-plugin/plugin.json` and the `@vX.Y.Z` git ref in
`plugin/.mcp.json`. Per the Claude Code docs, the marketplace entry carries no version; users
only receive a plugin update when the version in `plugin.json` changes.

1. On a branch, bump the version everywhere (`uv version --bump minor` for `pyproject.toml`,
   then `plugin.json` and `.mcp.json`), and update anything user-facing. Merge through a PR.
2. Tag the merge commit on `main` and push it: `git tag v0.2.0 && git push origin v0.2.0`.
3. `release.yml` runs CI, checks that the tag matches the package version, builds, and creates
   a GitHub Release with the wheel and sdist.
   - Plugin users get the new version with `claude plugin update forscore@forscore-mcp`, or
     automatically if they turned on auto-update.
   - `uvx --from git+…` users get it on the next run.
4. PyPI publishing is built in but off. To turn it on, once the repo is public and licensed:
   - Add a trusted publisher for this repo on PyPI, with workflow `release.yml` and
     environment `pypi`.
   - Set the repository variable `PUBLISH_ENABLED=true`.
   - Remove the `Private :: Do Not Upload` classifier.
   - Optionally switch `plugin/.mcp.json` to `uvx forscore-mcp@X.Y.Z`.

Before tagging, check the plugin locally:
- `claude plugin validate --strict plugin` and `claude plugin validate --strict .` (CI runs both).
- `claude --plugin-dir plugin`, then `/mcp` should show `forscore` as connected.
- `claude --plugin-dir plugin plugin details forscore`: keep the always-on cost small (about
  120 tokens at v0.1.1). The skill's `description` is what every session pays for.

Later options, once the project is public:
- Submit it to Anthropic's directory at claude.ai/directory/manage.
- Emit a `<claude-code-hint>` from the CLI. This only works for official marketplaces.
