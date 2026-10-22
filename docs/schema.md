# forScore library schema (reverse-engineered)

forScore (tested with 15.2 on macOS) stores its library in a Core Data SQLite database:

```
~/Library/Containers/com.mgsdevelopment.forscore/Data/Library/Preferences/library.4sl
```

Prior art: [forscore-cli](https://github.com/danielhopkins/forscore-cli) (Rust, MIT) edits the
same store and also writes the sync files. Its key decoding treats the middle digit as a sharp
flag, which does not match the data. Nothing here is a documented API. `schema.py` checks the parts listed below every time it opens
the store, and refuses to work with a store that does not match.

## Entities

`Z_PRIMARYKEY` maps entity names to ids (`Z_ENT`) and holds the per-entity primary-key counter
(`Z_MAX`). Sub-entities share their parent's table and counter.

| Entity | Table | Notes |
|---|---|---|
| Item | `ZITEM` | parent of Score and Bookmark |
| Score | `ZITEM` (`Z_ENT` = Score) | one PDF |
| Bookmark | `ZITEM` (`Z_ENT` = Bookmark) | page range within a score (`ZSCORE` → parent) |
| Meta | `ZMETA` | parent of Composer, Genre, Keyword, Label, Difficulty, Rating; new rows take `Z_MAX + 1` of **Meta** |

## Item columns used

| Column | Meaning |
|---|---|
| `ZUUID` | stable id, identical across synced devices |
| `ZTITLE`, `ZSORTTITLE` | title, and its sort form (leading article and punctuation removed) |
| `ZREFERENCE` | free-text reference field (Op./BWV/…) |
| `ZKEY` | three-digit key code (below) |
| `ZPATH` | PDF file name in the app's Documents folder |
| `Z_OPT`, `ZMODIFIED` | Core Data version counter; modification time in seconds since 2001-01-01 |

## Metadata values (`ZMETA`)

| Kind | Entity | Text column | Join table (item ↔ meta) |
|---|---|---|---|
| composers | Composer | `ZVALUE` (+ `ZLAST` = sort name) | `Z_4COMPOSERS` |
| genres | Genre | `ZVALUE2` | `Z_4GENRES` |
| tags | Keyword | `ZVALUE3` | `Z_4KEYWORDS` |
| labels | Label | `ZVALUE4` | `Z_4LABELS` |

Join-table and column names include entity ids (`Z_4ITEMS1`, `Z_10COMPOSERS`, …); `schema.py`
derives them instead of hard-coding them. Difficulty (`ZVALUE1`) and rating (`ZVALUE5`) are
not handled yet.

## Key code

`ZKEY` = note × 100 + accidental × 10 + mode, where note C=1 … B=7, accidental 0 = ♭,
1 = natural, 2 = ♯, and mode 0 = major, 1 = minor. 611 = A minor, 300 = E♭ major,
421 = F♯ minor. Confirmed against values set in the app.

forScore's CSV export and PDF-metadata import use a MIDI-style pair instead: `keysf`, the
number of sharps (negative for flats), and `keymi`, 0 for major and 1 for minor. A CSV export
from the app agrees with the code above for every score, for example 511 = −2/1 = G minor.

## Sync

forScore does **not** sync the database. It syncs one sync file per score,
`Preferences/Sync/<pdf name>.itm`, through iCloud. Each file is a gzipped binary plist holding
that score's metadata, pages and other data. The app rewrites a score's file whenever the
score is edited in the app.

The metadata keys this tool writes are `title`, `composer`, `genre`, `keywords` (tags),
`labels`, `reference` and `key` (the same code as `ZKEY`). Lists are joined with ", ", and an
empty value removes the key. `Sync/*.lib` files hold the libraries.

Editing only the database leaves the sync files stale, so other devices never see the change.
This happened on 2026-10-22: after a direct database edit, the iPad kept the old names for 40
scores. Bumping `Z_OPT` and `ZMODIFIED` is *not* enough.

`apply` therefore updates each changed score's sync file in the same step, and bumps
`Z_OPT`/`ZMODIFIED` so the database stays consistent. `forscore-mcp sync-check` (and the
`doctor` check) compares the two.

If they ever drift, force a full resync:
1. Turn sync off on the other devices.
2. On the Mac, turn sync off and on again, choosing to keep this device's data.
3. Turn sync back on on the other devices.

forScore must not be running during writes; otherwise it may overwrite the changes from memory.

## Official interfaces (for reference)

- URL scheme `forscore://open|service|action`: navigation only.
- Shortcuts (App Intents): the app declares metadata actions (`SetKey`, `SetReference`,
  `AddMetadataIntent`, `RemoveMetadataIntent`, `RenameScoreIntent`, …). This is a possible
  future backend that would not touch the database, but it needs user-built Shortcuts and is
  slow for bulk edits.
- Backups panel: CSV metadata import/export. The columns are `Filename, Title, Start Page
  (Bookmark), End Page (Bookmark), Composers, Genres, Tags, Labels, Reference, Rating,
  Difficulty, Minutes, Seconds, keysf, keymi`, with lists comma-separated. It is a possible
  officially supported write path.
- PDF metadata on import (Title, Author → composers, Subject → genres, Keywords → tags).
