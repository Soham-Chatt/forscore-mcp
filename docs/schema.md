# forScore library schema (reverse-engineered)

forScore (tested with 15.2 on macOS) stores its library in a Core Data SQLite database:

```
~/Library/Containers/com.mgsdevelopment.forscore/Data/Library/Preferences/library.4sl
```

Nothing here is a documented API. `schema.py` checks the parts listed below every time it opens
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

(forScore's PDF-metadata import uses a different, MIDI-style encoding, `keysf`/`keymi`. It is
not used in the database.)

## Sync

forScore syncs through CloudKit. Edits made directly in the database propagate to other devices
as long as forScore is **not running** during the write and every changed item gets
`Z_OPT + 1` and a fresh `ZMODIFIED`. This was confirmed by checking the changes on an iPad after
editing on the Mac. If forScore is open, it may overwrite the changes from memory.

## Official interfaces (for reference)

- URL scheme `forscore://open|service|action`: navigation only.
- Shortcuts (App Intents): the app declares metadata actions (`SetKey`, `SetReference`,
  `AddMetadataIntent`, `RemoveMetadataIntent`, `RenameScoreIntent`, …). This is a possible
  future backend that would not touch the database, but it needs user-built Shortcuts and is
  slow for bulk edits.
- Backups panel: CSV metadata import/export. The format is undocumented.
- PDF metadata on import (Title, Author → composers, Subject → genres, Keywords → tags).
