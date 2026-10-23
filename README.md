# forscore-mcp

Read and clean up the metadata in your [forScore](https://forscore.co) sheet-music library:
titles, composers, catalogue references (Op., BWV, K., …), keys, genres and tags. You can use
it through an AI assistant (MCP server and skill for Claude and other LLMs) or from the
command line.

> **Not affiliated with or endorsed by forScore LLC.** forScore is a trademark of forScore LLC.
> The tool reads forScore's internal library database (not a public API) and writes changes
> through forScore's own Metadata CSV import, as forScore recommends. Data is still injected
> into forScore as-is and cannot be guaranteed to work correctly or preserve existing data:
> always check forScore's import preview before tapping Save.

## What it does

- **Reads** every score and bookmark with its metadata (filtered and paged for big libraries),
  every composer, genre, tag, label and library in use, and your setlists.
- **Changes** metadata in bulk through a *changeset*: a small JSON file describing renames and
  per-score edits. Changesets are always previewed first and applied in a single transaction.
- **Writes the supported way:** changes become a CSV for forScore's Metadata import. The tool
  hands it to forScore. You open Backups › Metadata (CSV) › Import, tap the file, check
  forScore's own preview of every change and tap Save. forScore then handles the database and
  sync, and the tool verifies the result afterwards. Each import can be undone with another
  CSV.
- **Audits** the library for likely duplicates, identical PDFs, file names that differ from
  titles, and composer sort names worth checking.
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
forscore-mcp list chopin                  # search scores and bookmarks
forscore-mcp list --missing composers     # filters: --composer/--genre/--tag/--library/--kind
forscore-mcp show "Kinderszenen > Träumerei"   # one score or bookmark
forscore-mcp setlists                     # setlists and their items
forscore-mcp audit                        # duplicates, file names, sort names
forscore-mcp values composers             # all composers, with usage counts
forscore-mcp preview changes.json         # dry run (safe while forScore is open)
forscore-mcp apply changes.json --yes     # create the import CSV and send it to forScore
forscore-mcp verify <import id>           # after tapping Save in forScore: did it apply?
forscore-mcp undo <import id> --yes       # a CSV that restores the previous values
forscore-mcp sync-check                   # does the iPad get the same metadata?
forscore-mcp backups                      # list backups
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

`match` is a UUID, an exact title, or `"Score › Bookmark"` (`>` works too). `set` replaces
fields: `title`, `reference`, `key`, `rating` (0–5), `difficulty` (0–3), `duration` (`"m:ss"`),
`composers`, `genres`, `tags`, `labels` and `libraries` (libraries must already exist).
`add` and `remove` edit list fields. `sort_names` sets how composers are filed, e.g.
`{"Ralph Vaughan Williams": "Vaughan Williams"}`. Values nothing uses any more are removed
unless you pass `"prune": false`. PDF file names are never changed; rename those in forScore.

### MCP tools

| Tool | Writes? |
|---|---|
| `list_scores` (filters, paging), `get_score`, `list_values`, `list_setlists`, `audit_library`, `check_sync`, `convert_key`, `doctor`, `get_conventions` | no |
| `preview_changeset`, `list_backups`, `create_backup` | no (backups only) |
| `apply_changeset(changeset, confirm, method)`, `undo_import(import_id, confirm)` | creates an import for you to review in forScore; only with `confirm=true` |
| `verify_import(import_id)` | no |
| `apply_changeset(method="direct")`, `restore_backup` | danger zone only |

Configuration via environment: `FORSCORE_LIBRARY` (library path) and `FORSCORE_BACKUP_DIR`
(default `~/Library/Application Support/forscore-mcp/backups`).

## How it works

Reading: forScore keeps its library in a Core Data SQLite store. The tool opens it read-only,
validates its layout every time, and refuses anything it does not recognise. Details:
[`docs/schema.md`](docs/schema.md).

Writing: changes are written as forScore's Metadata CSV. forScore matches rows to scores by
file name, shows a per-field diff, and applies it on Save, including sync to your other
devices. Some changes have no CSV column; the tool lists them under "not in CSV" so you can make
them in forScore:
- library membership
- composer sort names
- keys with more than 7 sharps or flats
- values containing a comma

## Danger zone: direct database writes

> **Unsupported by forScore. Can cause crashes, unexpected behaviour or data loss.** forScore's
> developers advise against it. It bypasses forScore's own validation and edits the
> database and the per-score sync files directly.

For changes the CSV import cannot make, the tool can also write directly. This is off unless
you set this variable in the MCP server's environment (or your shell):

```
FORSCORE_DANGER_ZONE=i-understand-this-can-damage-my-library
```

Then `apply_changeset(..., method="direct")` or `forscore-mcp apply --direct --yes` works:
- forScore must be quit on the Mac, and a backup is made first.
- `restore` puts a backup back.
- `doctor` shows when the danger zone is on.

An assistant cannot turn it on by itself. Only that setting can.

## Development

```
uv sync
uv run pytest            # tests run against a synthetic library, never your real one
uv run ruff check . && uv run ruff format . && uv run ty check
```

See [`AGENTS.md`](AGENTS.md) for the architecture and contribution rules, and
[`docs/releasing.md`](docs/releasing.md) for releases.
