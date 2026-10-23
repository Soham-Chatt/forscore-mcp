import json
from pathlib import Path

import pytest

from forscore_mcp.cli import main
from forscore_mcp.library import Library

CHANGES = {"scores": [{"match": "Wet Hands", "set": {"key": "A minor"}}]}


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


@pytest.mark.usefixtures("library")
def test_list_and_show(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "list", "--json")
    assert code == 0
    assert json.loads(out)["total"] == 5
    _, out, _ = run(capsys, "show", "Wet Hands")
    assert "A major" in out
    _, out, _ = run(capsys, "values", "genres")
    assert "Soundtrack" in out


def test_preview_then_apply_writes_import(
    safe_library: Library,
    tmp_path: Path,
    delivered: list[Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    file = tmp_path / "changes.json"
    file.write_text(json.dumps(CHANGES))
    _, out, _ = run(capsys, "apply", str(file))
    assert "Preview only" in out
    assert not delivered
    code, out, _ = run(capsys, "apply", str(file), "--yes", "--json")
    assert code == 0
    report = json.loads(out)
    assert report["method"] == "csv"
    assert delivered == [Path(report["csv_file"])]
    assert safe_library.item("Wet Hands").key == "A major"  # unchanged until imported
    _, out, _ = run(capsys, "verify", report["import_id"])
    assert out.startswith("not imported yet")


def test_direct_needs_danger_zone(
    safe_library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    file = tmp_path / "changes.json"
    file.write_text(json.dumps(CHANGES))
    code, _, err = run(capsys, "apply", str(file), "--yes", "--direct")
    assert code == 1
    assert "Direct writes are disabled" in err


@pytest.mark.usefixtures("library")
def test_errors_are_friendly(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, "show", "Nope")
    assert code == 1
    assert err.startswith("error: No score")
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    assert run(capsys, "preview", str(bad))[0] == 1
    assert run(capsys, "restore", "x")[0] == 1


def test_key(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "key", "E♭ major")[1].strip() == "E♭ major = 300"
    assert json.loads(run(capsys, "key", "611", "--json")[1]) == {"name": "A minor", "code": 611}


@pytest.mark.usefixtures("safe_library")
def test_doctor_and_backups(capsys: pytest.CaptureFixture[str]) -> None:
    _, out, _ = run(capsys, "doctor")
    assert "4 scores, 1 bookmarks" in out
    assert run(capsys, "backups")[1].strip() == "No backups."
    run(capsys, "backup")
    assert len(json.loads(run(capsys, "backups", "--json")[1])) == 1


def test_conventions(capsys: pytest.CaptureFixture[str]) -> None:
    assert "Workflow" in run(capsys, "conventions")[1]
