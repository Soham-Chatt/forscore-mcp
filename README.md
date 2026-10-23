# forscore-mcp

Clean up the metadata in a [forScore](https://forscore.co) sheet-music library in bulk:
titles, composers, catalogue references (Op., BWV, K., …), keys, genres, tags, ratings and more.
It works through an AI assistant (an MCP server and a Claude Code plugin; Claude and other
LLMs) or from the command line.

> **Not affiliated with or endorsed by forScore LLC.** forScore is a trademark of forScore LLC.
> The tool reads forScore's internal library database, which is not a public API, and writes
> changes through forScore's own Metadata CSV import, as forScore's support recommends. Data
> is still injected into forScore as-is, and the tool cannot guarantee that it works
> correctly or preserves existing data. Always check forScore's import preview before tapping
> Save.

## Features

- **Read**:
  - every score and bookmark with its metadata (filtered and paged for large libraries)
  - every composer, genre, tag, label and library in use
  - setlists
- **Bulk-edit** titles, composers, references, keys, genres, tags, labels, rating,
  difficulty and duration, for scores and bookmarks.
- **Rename or merge** a composer, genre or tag everywhere it is used.
- **Audit** for likely duplicates, identical PDFs, file names that differ from titles, and
  composer sort names worth checking.
- **Check sync**: compare the library with what synced devices receive.
- **Conventions guide** for AI assistants, so their edits stay consistent: full composer
  names, `Op. 69 No. 2` references, genre as style period. See
  [`conventions.md`](src/forscore_mcp/conventions.md).

## How it works

1. **Read:** the tool opens forScore's library database on the Mac read-only and checks its
   layout every time. It refuses to work with anything it does not recognise.
2. **Propose:** the assistant (or you) writes a *changeset*, a small JSON description of the
   changes. It is previewed as a per-score diff, and nothing is written yet.
3. **Import:** the changeset becomes a CSV in forScore's own Metadata format, and the tool
   hands it to forScore. In forScore, open **Backups › Metadata (CSV) › Import**, tap the file,
   check forScore's preview and tap **Save**. forScore applies it and syncs it to your other
   devices.
4. **Verify or undo:** the tool checks field by field that the import applied. Any import can
   be reverted with a second, generated CSV.

forScore can stay open throughout.

## Requirements

- A Mac with forScore. The library database only exists on the Mac; iPad-only setups are not
  supported.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (`brew install uv`).
- **Full Disk Access** for the app that runs the tool (Terminal, Claude, Cursor, …), because
  forScore's data sits in a protected app container: System Settings › Privacy & Security ›
  Full Disk Access.

## Install

### Claude Code (plugin: MCP server + skill)

```
/plugin install forscore --marketplace Soham-Chatt/forscore-mcp
```

Or from a shell: `claude plugin install forscore --marketplace Soham-Chatt/forscore-mcp`.
On older Claude Code versions, run `/plugin marketplace add Soham-Chatt/forscore-mcp` and then
`/plugin install forscore@forscore-mcp`.

Update with `claude plugin update forscore@forscore-mcp`, or turn on auto-update under
**Marketplaces** in `/plugin`. The plugin needs Claude Code, or Claude Desktop through the
MCP configuration below. claude.ai on the web and Cowork cannot reach a Mac's local library.

### Other MCP clients (Claude Desktop, Cursor, VS Code, Codex, Gemini CLI, …)

Add the server to the client's MCP configuration. For Claude Desktop that is
`~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Agents without MCP support can use the CLI with `--json`; see [`AGENTS.md`](AGENTS.md).

### Command line

```
uv tool install git+https://github.com/Soham-Chatt/forscore-mcp
forscore-mcp doctor
```

`doctor` checks library access, sync state and the write mode, and explains how to fix any
problem it finds.

## Usage

Ask the assistant things like *"Clean up the composers in my forScore library"* or *"Fill in
the opus numbers for my Chopin scores"*. It follows the bundled
[conventions guide](src/forscore_mcp/conventions.md) unless told otherwise, and proposes a
table of changes. Once you approve them, it previews them and creates the import for
forScore.

Command line:

```
forscore-mcp list chopin                  # search scores and bookmarks
forscore-mcp list --missing composers     # filters: --composer --genre --tag --library --kind
forscore-mcp show "Kinderszenen > Träumerei"   # one score or bookmark
forscore-mcp values composers             # values in use, with counts and sort names
forscore-mcp setlists                     # setlists and their items
forscore-mcp audit                        # likely duplicates, file names, sort names
forscore-mcp preview changes.json         # dry run of a changeset
forscore-mcp apply changes.json --yes     # create the import CSV and hand it to forScore
forscore-mcp verify <import id>           # after Save in forScore: did everything apply?
forscore-mcp undo <import id> --yes       # a CSV that restores the previous values
forscore-mcp sync-check                   # do synced devices get the same metadata?
forscore-mcp key "E♭ major"               # key name ↔ forScore's internal code
```

Add `--json` to any command for machine-readable output.

### Changesets

See [`examples/changeset.example.json`](examples/changeset.example.json):

```json
{
  "renames": { "composers": { "Chopin": "Frédéric Chopin" } },
  "items": [
    { "match": "Fur Elise",
      "set": { "title": "Für Elise", "reference": "WoO 59", "key": "A minor", "genres": ["Classical"] },
      "add": { "tags": ["ABRSM Grade 5"] } },
    { "match": "Kinderszenen › Träumerei", "set": { "reference": "Op. 15 No. 7" } }
  ]
}
```

- `match`: a UUID, an exact title, or `"Score › Bookmark"` (`>` works too).
- `set` replaces these fields: `title`, `reference`, `key`, `rating` (0–5), `difficulty`
  (0–3), `duration` (`"m:ss"`), `composers`, `genres`, `tags` and `labels`.
- `add` and `remove` edit the list fields.
- `renames` renames a value everywhere it is used.

### What the CSV import cannot do

forScore's CSV format has no columns for these, so the tool lists them under "not in CSV"
instead of importing them:
- library membership
- composer sort names (`sort_names`)
- keys with more than 7 sharps or flats
- values containing a comma
- changing PDF file names

Make these changes in forScore itself. Changing a title in forScore can rename the PDF to
match.

### MCP tools

| Tool | Effect |
|---|---|
| `list_scores` (filters, paging), `get_score`, `list_values`, `list_setlists`, `audit_library`, `check_sync`, `convert_key`, `doctor`, `get_conventions` | read only |
| `preview_changeset` | read only (dry run) |
| `apply_changeset(changeset, confirm=true)`, `undo_import(import_id, confirm=true)` | creates an import CSV for review in forScore |
| `verify_import(import_id)` | read only |
| `create_backup`, `list_backups` | copies of the library database |
| `apply_changeset(method="direct")`, `restore_backup` | danger zone only (below) |

Environment variables:
- `FORSCORE_LIBRARY`: path to the library database.
- `FORSCORE_STATE_DIR`: where import CSVs are kept. The default is
  `~/Library/Application Support/forscore-mcp`.
- `FORSCORE_BACKUP_DIR`: where backups go.

## Danger zone: direct database writes

> **Unsupported by forScore. Can cause crashes, unexpected behaviour or data loss.**
> forScore's developers advise against it. It bypasses forScore's own validation and writes
> the database and the per-score sync files directly.

For the few changes the CSV import cannot make, the tool can write directly. It is off unless
this exact value is set in the MCP server's environment or the shell:

```
FORSCORE_DANGER_ZONE=i-understand-this-can-damage-my-library
```

What changes when it is on:
- `apply_changeset(..., method="direct")` and `forscore-mcp apply --direct --yes` write directly.
- forScore must be quit on the Mac during writes.
- A backup is made before every write, and `restore` puts one back.
- Values nothing uses any more are deleted. forScore hides them anyway, and each device keeps
  its own list.
- `doctor` shows that the danger zone is on.

An assistant cannot enable it through any tool call. Only that setting can.

## Limitations

- macOS only.
- Early (0.x), tested with forScore 15.2. A forScore update that changes the database layout
  makes the tool refuse to run until it is updated.
- Setlists are read-only.
- It's not yet confirmed whether the CSV import can update existing bookmarks' metadata;
  `verify` will show it either way.

## Contributing

Issues and pull requests are welcome, including reports from other forScore versions and
setups.

Development:

```
uv sync
uv run pytest            # tests use a synthetic library, never a real one
uv run ruff check . && uv run ruff format . && uv run ty check
```

[`AGENTS.md`](AGENTS.md) describes the architecture and rules; [`docs/schema.md`](docs/schema.md)
documents what is known about forScore's storage; [`docs/releasing.md`](docs/releasing.md)
covers releases.

## License

To be decided; until then, all rights reserved.
