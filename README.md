# forscore-mcp

Read and clean up the metadata in your [forScore](https://forscore.co) sheet-music library:
titles, composers, catalogue references (Op., BWV, K., …), keys, genres and tags. You can use
it through an AI assistant (MCP server and skill for Claude and other LLMs) or from the
command line.

> **Not affiliated with or endorsed by forScore LLC.** forScore is a trademark of forScore LLC.
> This tool edits forScore's internal library database, which is not a public API. It backs up
> before every write, but use it at your own risk.

## What it does

- **Reads** every score with its metadata, and every composer, genre, tag and label in use.
- **Changes** metadata in bulk through a *changeset*: a small JSON file describing renames and
  per-score edits. Changesets are always previewed first and applied in a single transaction.
- **Keeps you safe:** it writes only while forScore is closed on the Mac, makes an automatic
  backup before each write, runs integrity checks, and has one-command restore. Changes sync
  to your iPad and other devices through forScore's own sync.
- **Ships a conventions guide** (full composer names, `Op. 69 No. 2` references, genre = style
  period, …) so AI assistants make consistent choices. See
  [`conventions.md`](src/forscore_mcp/conventions.md).

## Requirements

- A Mac with forScore installed (the library database only exists on the Mac).
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (`brew install uv`).
- **Full Disk Access** for the app that runs the tool (Terminal, Claude, Cursor, …): System
  Settings › Privacy & Security › Full Disk Access. forScore's data sits in a protected app
  container.

## Install

### Claude Code (plugin: MCP server + skill)

In a Claude Code session:

```
/plugin install forscore --marketplace Soham-Chatt/forscore-mcp
```

Or from your shell: `claude plugin install forscore --marketplace Soham-Chatt/forscore-mcp`.
On older Claude Code versions, run `/plugin marketplace add Soham-Chatt/forscore-mcp` and then
`/plugin install forscore@forscore-mcp`.

- **Updates:** run `claude plugin update forscore@forscore-mcp`, or turn on auto-update under
  **Marketplaces** in `/plugin`.
- **While the repository is private**, Claude Code clones it with your own git credentials and
  can't prompt for them. Run `gh auth login` and `gh auth setup-git` once. If you have no GitHub
  SSH key, also set `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1`.
- **Supported apps:** the plugin works in Claude Code. On claude.ai and in Cowork it can't reach
  your Mac's library, so use Claude Code or Claude Desktop there.

### Any other MCP client (Claude Desktop, Cursor, VS Code, Codex, Gemini CLI, …)

Add this server to the client's MCP configuration (for Claude Desktop:
`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "forscore": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Soham-Chatt/forscore-mcp", "forscore-mcp"]
    }
  }
}
```

For agents without MCP support, point them at the CLI with `--json` and at
[`AGENTS.md`](AGENTS.md).

### Command line

```
uv tool install git+https://github.com/Soham-Chatt/forscore-mcp
forscore-mcp doctor
```

## Usage

Ask your assistant things like *"Clean up the composers in my forScore library"* or *"Fill in
the opus numbers for my Chopin scores"*. It reads the library, proposes a table of changes for
you to approve, previews them, asks you to quit forScore, and then applies them.

From the command line:

```
forscore-mcp doctor                       # check access; tells you how to fix problems
forscore-mcp list chopin                  # search scores
forscore-mcp show "Für Elise"             # one score's metadata
forscore-mcp values composers             # all composers, with usage counts
forscore-mcp preview changes.json         # dry run (safe while forScore is open)
forscore-mcp apply changes.json --yes     # back up, then apply (quit forScore first)
forscore-mcp sync-check                   # does the iPad get the same metadata?
forscore-mcp backups                      # list backups
forscore-mcp restore <id> --yes           # undo
forscore-mcp key "E♭ major"               # key name ↔ forScore's code
```

Add `--json` to any command for machine-readable output. A changeset looks like
[`examples/changeset.example.json`](examples/changeset.example.json):

```json
{
  "renames": { "composers": { "Chopin": "Frédéric Chopin" } },
  "scores": [
    { "match": "Fur Elise",
      "set": { "title": "Für Elise", "reference": "WoO 59", "key": "A minor", "genres": ["Classical"] },
      "add": { "tags": ["ABRSM Grade 5"] } }
  ]
}
```

`match` is a score's UUID or exact title. `set` replaces fields (`title`, `reference`, `key`,
`composers`, `genres`, `tags`, `labels`); `add` and `remove` edit list fields. Values no score
uses any more are removed unless you pass `"prune": false`.

### MCP tools

| Tool | Writes? |
|---|---|
| `list_scores`, `get_score`, `list_values`, `check_sync`, `convert_key`, `doctor`, `get_conventions` | no |
| `preview_changeset`, `list_backups`, `create_backup` | no (backups only) |
| `apply_changeset(changeset, confirm)`, `restore_backup(backup_id, confirm)` | yes, only with `confirm=true` |

Configuration via environment: `FORSCORE_LIBRARY` (library path) and `FORSCORE_BACKUP_DIR`
(default `~/Library/Application Support/forscore-mcp/backups`).

## How it works

forScore keeps its library in a Core Data SQLite store. This tool validates the store's layout
on every open (and refuses to write to anything it does not recognise), edits the relevant rows,
bumps each changed item's Core Data version and modification date, and updates the score's
sync file. forScore syncs those files, not the database, to your other devices.
`forscore-mcp sync-check` confirms that both agree. Details: [`docs/schema.md`](docs/schema.md).

## Development

```
uv sync
uv run pytest            # tests run against a synthetic library, never your real one
uv run ruff check . && uv run ruff format . && uv run ty check
```

See [`AGENTS.md`](AGENTS.md) for the architecture and contribution rules, and
[`docs/releasing.md`](docs/releasing.md) for releases.
