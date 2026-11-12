# Contributing

Bug reports, reports from other forScore setups, and pull requests are welcome.

## Reporting a problem

Open an issue and include:

- the output of `forscore-mcp doctor`
- your forScore version and macOS version
- what you ran or asked the assistant, and what happened
- for CSV imports: what forScore's import preview showed (a screenshot helps)

Never attach your library database or backups. They contain your whole library.

## Development

```
uv sync
uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest
```

- Work on a branch and open a pull request against `main`. CI must pass.
- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, …).
- After changing an MCP tool or CLI command, regenerate the reference:
  `uv run python scripts/gen_reference.py`.
- Tests use a synthetic library built from the real schema (`tests/conftest.py`), never a real
  one.

[`AGENTS.md`](AGENTS.md) describes the architecture and the rules every change must keep, and
[`docs/schema.md`](docs/schema.md) documents what is known about forScore's storage. If you
learn something new about it, please add it there.
