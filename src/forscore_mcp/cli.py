"""`forscore-mcp` command line. With no arguments it runs the MCP server (what MCP clients do)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from . import __version__, conventions, keys
from .doctor import run_checks
from .errors import ForScoreError
from .library import Library
from .models import MetaKind, Score


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in (None, "serve"):
        from .server import main as serve  # import lazily: only the server needs the MCP SDK

        serve()
        return 0
    try:
        result = args.handler(args)
    except (ForScoreError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if result is not None:
        data, text = result
        print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else text)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forscore-mcp", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", metavar="command")

    def command(name: str, handler: Callable[[argparse.Namespace], Any], help: str):
        p = sub.add_parser(name, parents=[common], help=help, description=help)
        p.set_defaults(handler=handler)
        return p

    sub.add_parser("serve", help="run the MCP server over stdio (default)")
    command("doctor", _doctor, "check library access and whether changes can be applied")
    command("list", _list, "list scores").add_argument("query", nargs="?")
    command("show", _show, "show one score by UUID or title").add_argument("match")
    command("values", _values, "list values of a category").add_argument(
        "kind", type=MetaKind, choices=list(MetaKind)
    )
    command("preview", _preview, "dry-run a changeset file ('-' for stdin)").add_argument("file")
    apply = command("apply", _apply, "apply a changeset file (backup first)")
    apply.add_argument("file")
    apply.add_argument("--yes", action="store_true", help="actually write (default: preview)")
    command("sync-check", _sync_check, "compare the library with what syncs to other devices")
    command("backup", _backup, "back up the library now")
    command("backups", _backups, "list backups")
    restore = command("restore", _restore, "restore a backup")
    restore.add_argument("backup_id")
    restore.add_argument("--yes", action="store_true", help="confirm overwriting the library")
    command("key", _key, "convert a key name to its code or back").add_argument("value")
    command("conventions", _conventions, "print the metadata conventions guide")
    return parser


# Each handler returns (json_data, human_text).


def _doctor(_: argparse.Namespace) -> tuple[Any, str]:
    checks = run_checks()
    text = "\n".join(f"{'✓' if c.ok else '✗'} {c.name}: {c.detail}" for c in checks)
    return [c.to_dict() for c in checks], text


def _list(args: argparse.Namespace) -> tuple[Any, str]:
    scores = Library().scores(args.query)
    lines = [_summary(s) for s in scores] + [f"\n{len(scores)} scores"]
    return [s.to_dict() for s in scores], "\n".join(lines)


def _show(args: argparse.Namespace) -> tuple[Any, str]:
    score = Library().score(args.match)
    data = score.to_dict()
    width = max(map(len, data))
    text = "\n".join(f"{k.ljust(width)}  {_fmt(v)}" for k, v in data.items())
    return data, text


def _values(args: argparse.Namespace) -> tuple[Any, str]:
    values = Library().values(args.kind)
    return [v.to_dict() for v in values], "\n".join(f"{v.count:4}  {v.value}" for v in values)


def _preview(args: argparse.Namespace) -> tuple[Any, str]:
    return _report(Library().preview(_read_json(args.file)).to_dict())


def _apply(args: argparse.Namespace) -> tuple[Any, str]:
    library = Library()
    data = _read_json(args.file)
    data, text = _report((library.apply(data) if args.yes else library.preview(data)).to_dict())
    if not args.yes:
        text += "\n\nPreview only. Quit forScore on the Mac, then re-run with --yes to apply."
    return data, text


def _sync_check(_: argparse.Namespace) -> tuple[Any, str]:
    drift = Library().sync_drift()
    lines = [
        f"{d.score}: {d.field} syncs as {_fmt(d.sync_file)}, library has {_fmt(d.library)}"
        for d in drift
    ]
    return [d.to_dict() for d in drift], "\n".join(lines) or "In sync."


def _backup(_: argparse.Namespace) -> tuple[Any, str]:
    backup = Library().backup()
    return backup.to_dict(), f"Backup {backup.id} written to {backup.path}"


def _backups(_: argparse.Namespace) -> tuple[Any, str]:
    backups = Library().backups()
    return [b.to_dict() for b in backups], "\n".join(b.id for b in backups) or "No backups."


def _restore(args: argparse.Namespace) -> tuple[Any, str]:
    if not args.yes:
        raise ValueError("Restoring overwrites the library; re-run with --yes to confirm.")
    previous = Library().restore(args.backup_id)
    return (
        {"restored": args.backup_id, "previous_state_backup": previous.id},
        f"Restored {args.backup_id}. The state before restoring is saved as {previous.id}.",
    )


def _key(args: argparse.Namespace) -> tuple[Any, str]:
    value = args.value.strip()
    code = int(value) if value.isdigit() else keys.encode(value)
    name = keys.decode(code)
    return {"name": name, "code": code}, f"{name} = {code}"


def _conventions(_: argparse.Namespace) -> tuple[Any, str]:
    text = conventions()
    return {"conventions": text}, text


# ---- formatting helpers ----------------------------------------------------------------


def _read_json(file: str) -> Any:
    raw = sys.stdin.read() if file == "-" else Path(file).read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{file} is not valid JSON: {exc}") from exc


def _report(report: dict[str, Any]) -> tuple[Any, str]:
    if not (report["changes"] or report["renamed"] or report["pruned"]):
        return report, "No changes."
    lines = []
    for kind, mapping in report["renamed"].items():
        lines += [f"rename {kind}: {old} → {new}" for old, new in mapping.items()]
    for title, fields in report["changes"].items():
        lines.append(title)
        lines += [f"    {f}: {_fmt(b)} → {_fmt(a)}" for f, (b, a) in fields.items()]
    for kind, values in report["pruned"].items():
        lines.append(f"remove unused {kind}: {', '.join(values)}")
    lines.append(f"\n{report['scores_changed']} scores changed")
    if report["backup"]:
        lines.append(f"{report['sync_files_updated']} sync files updated")
        lines.append(f"Backup: {report['backup']}")
    return report, "\n".join(lines)


def _summary(score: Score) -> str:
    extra = " · ".join(
        filter(None, [", ".join(score.composers), score.reference, ", ".join(score.genres)])
    )
    return f"{score.title}  ({extra})" if extra else score.title


def _fmt(value: Any) -> str:
    if value is None or value == []:
        return "—"
    return ", ".join(value) if isinstance(value, list) else str(value)


if __name__ == "__main__":
    raise SystemExit(main())
