"""`forscore-mcp` command line. With no arguments it runs the MCP server (what MCP clients do)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from . import __version__, conventions, keys, safety
from .doctor import run_checks
from .errors import ForScoreError
from .library import Filters, Library
from .models import FIELDS, Item, ItemKind, MetaKind


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
    ls = command("list", _list, "list scores and bookmarks")
    ls.add_argument("query", nargs="?", help="search titles, references, composers, tags")
    ls.add_argument("--kind", type=ItemKind, choices=list(ItemKind))
    for name in ("composer", "genre", "tag", "label", "library"):
        ls.add_argument(f"--{name}", help=f"exact {name} (case-insensitive)")
    ls.add_argument("--missing", choices=FIELDS, help="only items where this field is empty")
    ls.add_argument("--limit", type=int, default=None)
    ls.add_argument("--offset", type=int, default=0)
    command("show", _show, "show one item by UUID, title or 'Score > Bookmark'").add_argument(
        "match"
    )
    command("values", _values, "list values of a category").add_argument(
        "kind", type=MetaKind, choices=list(MetaKind)
    )
    command("preview", _preview, "dry-run a changeset file ('-' for stdin)").add_argument("file")
    apply = command("apply", _apply, "write a changeset as a forScore import CSV")
    apply.add_argument("file")
    apply.add_argument("--yes", action="store_true", help="actually write (default: preview)")
    apply.add_argument(
        "--direct", action="store_true", help="write the database directly (needs direct writes on)"
    )
    command("verify", _verify, "check that forScore applied an import").add_argument("import_id")
    undo = command("undo", _undo, "create a CSV that reverts an import")
    undo.add_argument("import_id")
    undo.add_argument("--yes", action="store_true", help="confirm creating the undo import")
    command("setlists", _setlists, "list setlists and their items")
    command("audit", _audit, "find duplicates, file-name mismatches and sort-name issues")
    command("sync-check", _sync_check, "compare the library with what syncs to other devices")
    command("backup", _backup, "back up the library now")
    command("backups", _backups, "list backups")
    restore = command("restore", _restore, "restore a backup")
    restore.add_argument("backup_id")
    restore.add_argument("--yes", action="store_true", help="confirm overwriting the library")
    direct = command(
        "direct-writes", _direct_writes, "turn unsupported direct database writes on or off"
    )
    direct.add_argument("action", choices=["status", "enable", "disable"])
    direct.add_argument("phrase", nargs="?", help="required to enable; run without it to see it")
    command("key", _key, "convert a key name to its code or back").add_argument("value")
    command("conventions", _conventions, "print the metadata conventions guide")
    return parser


# Each handler returns (json_data, human_text).


def _doctor(_: argparse.Namespace) -> tuple[Any, str]:
    checks = run_checks()
    text = "\n".join(f"{'✓' if c.ok else '✗'} {c.name}: {c.detail}" for c in checks)
    return [c.to_dict() for c in checks], text


def _list(args: argparse.Namespace) -> tuple[Any, str]:
    filters = Filters(
        args.query, args.kind, args.composer, args.genre, args.tag, args.label, args.library,
        args.missing,
    )  # fmt: skip
    page = Library().page(filters, offset=args.offset, limit=args.limit or 10**9)
    lines = [_summary(i) for i in page.items]
    shown = f"{len(page.items)} of {page.total}" if len(page.items) < page.total else page.total
    lines.append(f"\n{shown} items")
    data = {"total": page.total, "offset": page.offset, "items": [i.to_dict() for i in page.items]}
    return data, "\n".join(lines)


def _show(args: argparse.Namespace) -> tuple[Any, str]:
    data = Library().item(args.match).to_dict()
    width = max(map(len, data))
    text = "\n".join(f"{k.ljust(width)}  {_fmt(v)}" for k, v in data.items())
    return data, text


def _values(args: argparse.Namespace) -> tuple[Any, str]:
    values = Library().values(args.kind)
    lines = [
        f"{v.count:4}  {v.value}" + (f"  (sorted as {v.sort_name})" if v.sort_name else "")
        for v in values
    ]
    return [v.to_dict() for v in values], "\n".join(lines)


def _setlists(_: argparse.Namespace) -> tuple[Any, str]:
    setlists = Library().setlists()
    lines = [f"{s.title}\n" + "".join(f"  {n}. {i}\n" for n, i in enumerate(s.items, 1))
             for s in setlists]  # fmt: skip
    return [s.to_dict() for s in setlists], "\n".join(lines).rstrip() or "No setlists."


def _audit(_: argparse.Namespace) -> tuple[Any, str]:
    report = Library().audit()
    lines = []
    for group in report.duplicate_titles:
        lines.append(f"similar titles: {' | '.join(group)}")
    for group in report.identical_files:
        lines.append(f"identical PDFs: {' | '.join(group)}")
    for entry in report.filename_mismatches:
        lines.append(f"file name differs: {entry['item']}  ({entry['file']})")
    for entry in report.sort_names:
        lines.append(f"sort name: {entry['composer']} → {entry['sort_name']}: {entry['reason']}")
    return report.to_dict(), "\n".join(lines) or "Nothing to report."


def _preview(args: argparse.Namespace) -> tuple[Any, str]:
    return _report(Library().preview(_read_json(args.file)).to_dict())


def _apply(args: argparse.Namespace) -> tuple[Any, str]:
    library = Library()
    data = _read_json(args.file)
    method = "direct" if args.direct else "csv"
    report = library.apply(data, method=method) if args.yes else library.preview(data)
    result, text = _report(report.to_dict())
    if not args.yes:
        text += "\n\nPreview only. Re-run with --yes to create the import for forScore."
    return result, text


def _verify(args: argparse.Namespace) -> tuple[Any, str]:
    result = Library().verify_import(args.import_id)
    lines = [f"{result['status']} ({result['items']} items)"]
    lines += [f"  {m['item']}: {m['field']} is {_fmt(m['actual'])}, expected {_fmt(m['expected'])}"
              for m in result["mismatches"]]  # fmt: skip
    return result, "\n".join(lines)


def _undo(args: argparse.Namespace) -> tuple[Any, str]:
    if not args.yes:
        raise ValueError("Undo creates a new import for forScore; re-run with --yes to confirm.")
    result = Library().undo_import(args.import_id)
    return result, str(result["next_step"])


def _sync_check(_: argparse.Namespace) -> tuple[Any, str]:
    drift = Library().sync_drift()
    lines = [
        f"{d.item}: {d.field} syncs as {_fmt(d.sync_file)}, library has {_fmt(d.library)}"
        for d in drift
    ]
    return [d.to_dict() for d in drift], "\n".join(lines) or "In sync."


def _backup(_: argparse.Namespace) -> tuple[Any, str]:
    backup = Library().backup()
    return backup.to_dict(), f"Backup {backup.id} written to {backup.path}"


def _backups(_: argparse.Namespace) -> tuple[Any, str]:
    backups = Library().backups()
    return [b.to_dict() for b in backups], "\n".join(b.id for b in backups) or "No backups."


def _restore(
    args: argparse.Namespace,
) -> tuple[Any, str]:  # direct writes only (checked in Library)
    if not args.yes:
        raise ValueError("Restoring overwrites the library; re-run with --yes to confirm.")
    previous = Library().restore(args.backup_id)
    return (
        {"restored": args.backup_id, "previous_state_backup": previous.id},
        f"Restored {args.backup_id}. The state before restoring is saved as {previous.id}.",
    )


def _direct_writes(args: argparse.Namespace) -> tuple[Any, str]:
    if args.action == "enable":
        if args.phrase != safety.DIRECT_WRITES_PHRASE:
            problem = "No confirmation phrase given." if not args.phrase else "Wrong phrase."
            raise ValueError(
                f"{problem} {safety.DIRECT_WRITES_RISK}\nTo accept the risk, run:\n"
                f"  {safety.ENABLE_COMMAND}"
            )
        safety.set_direct_writes(True)
    elif args.action == "disable":
        safety.set_direct_writes(False)
    enabled = safety.direct_writes_enabled()
    text = (
        "Direct writes are ON (unsupported by forScore; a backup is made before each write). "
        "Turn off with `forscore-mcp direct-writes disable`."
        if enabled
        else "Direct writes are off: changes go through forScore's CSV import."
    )
    if args.action == "disable" and enabled:
        text += f" (Still on through the {safety.DIRECT_WRITES_ENV} environment variable.)"
    return {"direct_writes": enabled}, text


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
    if not (report["changes"] or report["renamed"] or report["sort_names"] or report["pruned"]):
        return report, "No changes."
    lines = []
    for kind, mapping in report["renamed"].items():
        lines += [f"rename {kind}: {old} → {new}" for old, new in mapping.items()]
    for title, fields in report["changes"].items():
        lines.append(title)
        lines += [f"    {f}: {_fmt(b)} → {_fmt(a)}" for f, (b, a) in fields.items()]
    for composer, sort_name in report["sort_names"].items():
        lines.append(f"sort name {composer}: {sort_name}")
    for kind, values in report["pruned"].items():
        lines.append(f"remove unused {kind}: {', '.join(values)}")
    lines.append(f"\n{report['items_changed']} items changed")
    if report["backup"]:
        lines.append(f"{report['sync_files_updated']} sync files updated")
        lines.append(f"Backup: {report['backup']}")
    for name, reasons in report.get("skipped", {}).items():
        lines.append(f"not in CSV: {name}: {'; '.join(reasons)}")
    if report.get("warning"):
        lines.append(f"\n⚠ {report['warning']}")
    if report.get("next_step"):
        lines.append(f"\n{report['next_step']}")
    return report, "\n".join(lines)


def _summary(item: Item) -> str:
    extra = " · ".join(
        filter(None, [", ".join(item.composers), item.reference, ", ".join(item.genres)])
    )
    name = f"  └ {item.title} (p. {item.pages})" if item.parent else item.title
    return f"{name}  ({extra})" if extra else name


def _fmt(value: Any) -> str:
    if value is None or value == []:
        return "—"
    return ", ".join(value) if isinstance(value, list) else str(value)


if __name__ == "__main__":
    raise SystemExit(main())
