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
| Composer sort name | How forScore files the composer, normally the surname (`Beethoven` for Ludwig van Beethoven). Fix compound or unusual surnames with `sort_names`: `Vaughan Williams`, `Lloyd Webber`, `Rimsky-Korsakov`; group or alias names sort as written without a leading article. | |
| Bookmarks | A piece inside a collection (e.g. *Kinderszenen › Träumerei*) gets the same rules as a score: its own title, composer, reference (`Op. 15 No. 7`), key. | |
| Rating, difficulty, duration | Personal (rating 1–5, difficulty 1–3) or performance-specific (`m:ss`); set only when the user gives them. | |
| Labels, libraries, folders, setlists | The user's own organisation; change only when asked. Libraries must already exist in forScore. | |

## Workflow

1. Read the library page by page (`list_scores`, filtered e.g. `missing="composers"`),
   `list_values` and `audit_library`. Note inconsistencies: duplicates, typos ("Lizst"),
   surnames vs full names, file-name-style titles (`Kabalevskij_op.39_24`), missing
   references/genres, odd composer sort names.
2. Propose the changes to the user as a table (current → proposed) and ask about anything
   uncertain (e.g. which piece a file really contains). Never invent catalogue numbers.
3. Write the approved changes as one changeset. Use `renames` for values used by many scores.
   PDF file names cannot be changed by the tool; tell the user to rename them in forScore
   (changing a title there can rename the file).
4. `preview_changeset` and show the user the summary, including anything listed under
   `skipped` (changes the CSV import cannot make).
5. `apply_changeset` with `confirm=true`. This creates an import CSV and sends it to forScore;
   nothing changes yet. Tell the user the `next_step`: in forScore, open Backups › Metadata
   (CSV) › Import, tap the file, check forScore's preview and tap Save.
6. When the user says they saved, call `verify_import` and report the result. If something is
   wrong, `undo_import` creates a CSV that restores the previous values.
7. Skipped changes (library membership, composer sort names): ask the user to make them in
   forScore. Only if the user has enabled the danger zone themselves, and agrees, use
   `apply_changeset(method="direct")`. It needs forScore quit on the Mac, and it is not
   supported by forScore.
