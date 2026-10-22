# Releasing

One version number, kept in four places (`tests/test_versions.py` fails if they drift):
`pyproject.toml`, `.claude-plugin/marketplace.json`, `plugin/.claude-plugin/plugin.json`, and
the `@vX.Y.Z` git ref in `plugin/.mcp.json`.

1. On a branch, bump the version everywhere (`uv version --bump minor` for `pyproject.toml`,
   then the three plugin files), and update anything user-facing. Merge through a PR.
2. Tag the merge commit on `main` and push it: `git tag v0.2.0 && git push origin v0.2.0`.
3. `release.yml` runs CI, checks that the tag matches the package version, builds, and creates
   a GitHub Release with the wheel and sdist.
   - Plugin users get the new version through `/plugin marketplace update`.
   - `uvx --from git+…` users get it on the next run.
4. PyPI publishing is built in but off. To turn it on, once the repo is public and licensed:
   - Add a trusted publisher for this repo on PyPI, with workflow `release.yml` and
     environment `pypi`.
   - Set the repository variable `PUBLISH_ENABLED=true`.
   - Remove the `Private :: Do Not Upload` classifier.
   - Optionally switch `plugin/.mcp.json` to `uvx forscore-mcp@X.Y.Z`.
