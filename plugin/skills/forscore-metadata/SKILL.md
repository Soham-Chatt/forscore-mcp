---
name: forscore-metadata
description: Clean up, standardise or fill in metadata in the user's forScore sheet-music library (titles, composers, Op./BWV/K. references, keys, genres, tags). Use when the user mentions forScore, their sheet-music/score library, inconsistent score names, or missing composer/opus/key information.
---

# forScore metadata

Use the `forscore` MCP tools. They read the library directly and write through a safe,
backed-up, single-transaction changeset.

1. Call `get_conventions` first and follow it; it is the single source of truth for naming
   rules and the editing workflow.
2. Call `doctor` if anything fails; relay its fix to the user verbatim.
3. Read with `list_scores` / `list_values`; propose changes to the user as a table
   (current → proposed) and wait for approval. Ask rather than guess when unsure which piece a
   file contains or what its key or catalogue number is.
4. Build one changeset, run `preview_changeset`, and summarise the diff.
5. Ask the user to quit forScore on the Mac, then `apply_changeset` with `confirm=true`.
   Report the backup id, and ask the user to reopen forScore and check that the iPad synced.

Never call `apply_changeset` or `restore_backup` with `confirm=true` without the user's
explicit go-ahead for that exact change.
