# AGENTS.md

Guide for AI coding agents (Claude Code, Codex, Cursor, Gemini, …) working on this repository,
and for agents *using* the tool through its CLI.

## Using the tool (no MCP)

Run `forscore-mcp conventions` and follow it. Read with `forscore-mcp list --json` and
`forscore-mcp values <kind> --json`; write a changeset file, run `forscore-mcp preview <file>`, get the user's approval, then
`forscore-mcp apply <file> --yes`. It creates an import CSV; the user imports it in forScore
(Backups › Metadata › Import); then `forscore-mcp verify <import id>`. Never pass `--yes`
without explicit user approval, and never turn on direct writes yourself.

## Architecture

`src/forscore_mcp/`, layered bottom-up; each layer only imports the ones above it:

| Module | Role |
|---|---|
| `errors.py`, `models.py` | exceptions (user-facing messages) and plain dataclasses |
| `keys.py`, `sorttitle.py` | pure helpers: key codec, sort-title normalisation |
| `paths.py` | default locations, overridable by env vars |
| `schema.py` | discovers and validates the Core Data layout; raises `SchemaError` |
| `db.py` | connections (read-only by default), in-memory snapshots, transactions |
| `safety.py` | forScore-running guard, backup / restore (database + sync files) |
| `csvimport.py` | default write path: forScore Metadata CSV, delivery, verify, undo |
| `syncfiles.py` | per-score `.itm` sync files: read, update, drift check |
| `repository.py` | `Store`: read and write primitives on one connection, no policy |
| `changeset.py` | parse/validate changesets, run them on a `Store`, produce a diff `Report` |
| `library.py` | `Library`: the public API; all safety policy lives here |
| `audit.py` | read-only health checks: duplicates, file names, sort names |
| `doctor.py` | environment checks |
| `cli.py`, `server.py` | thin front-ends over `Library`; no business logic |
| `conventions.md` | metadata conventions, shipped in the package; single source of truth |

Front-ends must stay thin: a new capability goes into `Library` (and below) first, then gets
exposed by both the CLI and the MCP server.

## Rules

- `uv` only. Before committing: `uv run ruff format . && uv run ruff check . && uv run ty check
  && uv run pytest`. CI enforces all four.
- Tests use the synthetic library in `tests/conftest.py`, built from the real schema DDL in
  `tests/fixtures/schema.sql`. Never commit a real library, backups or personal changesets
  (`local/` is gitignored for those).
- The default write path is the CSV import (`Library.apply`, method "csv"). Direct writes
  (method "direct") must stay behind `safety.require_direct_writes()`; only the user turns
  them on (`forscore-mcp direct-writes enable <phrase>`), never an MCP tool.
- Every direct write path goes through `Library`, which must keep: refusing to write while forScore runs
  (`safety.require_quit`), a backup before writing, one transaction, integrity checks,
  `Store.touch` on changed items, and updating their sync files (`syncfiles.update`). Other
  devices only see what is in the sync files.
- After changing an MCP tool or CLI command, run `uv run python scripts/gen_reference.py`. It
  regenerates `docs/reference.md` from the docstrings and type hints, and CI fails if the file
  is out of date. Tool docstrings are the user-facing documentation: keep them accurate.
- Schema knowledge belongs in `schema.py` and `docs/schema.md`. If you discover something new about
  forScore's store, document it there.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `ci:`, `chore:`, `test:`, `refactor:`); work
  on a branch and merge to `main` through a pull request with green CI.
- The version lives in `pyproject.toml`, `plugin/.claude-plugin/plugin.json` and `plugin/.mcp.json`
  (never in `marketplace.json`);
  `tests/test_versions.py` keeps them in sync. See `docs/releasing.md`.
