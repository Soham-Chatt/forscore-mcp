# forScore metadata conventions

Use these rules when proposing metadata for a forScore library, so every score reads the same
way. Follow the user's own choices where they differ, and keep a library's existing style if it
is already consistent.

## Fields

| Field | Rule | Examples |
|---|---|---|
| Title | The name the piece is most widely known by. Named works keep their original language; generic form titles are in English. Catalogue numbers do **not** go in the title. Lower-case mode in key names. | *Für Elise*, *Kinderszenen*, *Gymnopédies*, *La cloche sonne*; *Waltz in B minor*, *Bagatelle in G minor*, *Prelude in C major (WTC I)* |
| Composer | Full name in its usual form. One composer per value; several composers are separate values. Arrangers are not composers. Game/film/TV music: the actual composer, not the franchise. | Ludwig van Beethoven, Frédéric Chopin, Franz Liszt; "Mahito Yokota" + "Koji Kondo" |
| Reference | Catalogue identifiers in standard form: `Op. 69 No. 2`, `BWV 846`, `BWV Anh. 115`, `WoO 59`, `S. 238`, `D. 145 (Op. 18)`, `L. 68`, `Sz. 107`, `K. 545`, `Hob. XVI:35`, `B. 150`. A movement within an opus: `Op. 100 No. 20`. | |
| Key | Only for single pieces, and only when certain (C major and A minor share a key signature — check the music). Leave empty for collections. | A minor, E♭ major, F♯ minor |
| Genre | One style period: Baroque, Classical, Romantic, Impressionist, 20th Century, Contemporary, Soundtrack. Soundtrack covers game, film, TV and anime music. | |
| Tags | The source franchise (Pokemon, Super Mario Galaxy, How to Train Your Dragon); exam syllabus (`ABRSM Grade 5`); type (`Etudes`, `Technique`, `Collection` for multi-piece books). | |
| Labels, folders, setlists, rating, difficulty | Leave unless the user asks; these reflect personal organisation. | |

## Workflow

1. Read the library (`list_scores`, `list_values`) and note inconsistencies: duplicates, typos
   ("Lizst"), surnames vs full names, file-name-style titles (`Kabalevskij_op.39_24`), missing
   references/genres.
2. Propose the changes to the user as a table (current → proposed) and ask about anything
   uncertain (e.g. which piece a file really contains). Never invent catalogue numbers.
3. Write the approved changes as one changeset. Use `renames` for values used by many scores.
4. `preview_changeset` and show the user the summary.
5. Ask the user to **quit forScore on the Mac** (the iPad can stay open), then
   `apply_changeset` with `confirm=true`. A backup is made automatically.
6. Check that `sync_files_updated` in the report matches the number of scores changed. Ask the
   user to open forScore on the Mac, wait a minute, and check the iPad. `check_sync` should
   return nothing. If anything is wrong, `restore_backup` with the backup id from the apply
   report.
