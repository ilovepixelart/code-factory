"""`code-factory config check|show`, `docs --out` and `intake-key list|revoke`, through the real
command line for what needs no database and through the command's runner for the rest."""

from pathlib import Path

import pytest

from code_factory import app as composition_root
from repo_files import ROOT


def docs(out: Path) -> int:
    return composition_root.main(["docs", "--out", str(out)])


def test_docs_writes_its_pages_and_prints_their_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "made" / "here"
    assert docs(out) == 0
    assert capsys.readouterr().out.splitlines() == [
        str(out / "commands.md"),
        str(out / "config.md"),
        str(out / "modules.md"),
        str(out / "feature-map.md"),
        str(out / "database-tables.md"),
    ]
    assert "| `runs` |" in (out / "modules.md").read_text()
    commands = (out / "commands.md").read_text()
    assert "## code-factory config" in commands.splitlines()
    assert "## code-factory docs" in commands.splitlines()
    assert "- `--out`" in commands


def test_docs_refuses_an_out_that_is_a_file_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("notes\n")
    assert docs(notes) == 2
    assert f"{notes} is not a folder" in capsys.readouterr().err
    assert notes.read_text() == "notes\n"
    assert [p.name for p in tmp_path.iterdir()] == ["notes.txt"]


def test_docs_lists_every_table_with_its_columns_types_defaults_and_keys(tmp_path: Path) -> None:
    assert docs(tmp_path) == 0
    lines = (tmp_path / "database-tables.md").read_text().splitlines()
    # Expected rows are the ones the tickets migration creates.
    assert "### tickets" in lines
    assert "| `number` | `BIGINT` | no | identity | primary key |" in lines
    assert "| `title` | `TEXT` | no |  |  |" in lines
    assert "| `type` | `TEXT` | no | `'feature'` |  |" in lines
    assert "| `labels` | `TEXT[]` | no | `'{}'` |  |" in lines
    assert "| `ticket_number` | `BIGINT` | no |  | `tickets.number` |" in lines
    assert (
        lines.index("## tickets") < lines.index("### tickets") < lines.index("### ticket_activity")
    )
    # A table the platform owns comes first, before any module's.
    assert lines.index("## platform") < lines.index("### schema_info") < lines.index("## auth")


def test_docs_feature_map_is_a_tree_of_each_module_and_what_it_serves(tmp_path: Path) -> None:
    assert docs(tmp_path) == 0
    lines = (tmp_path / "feature-map.md").read_text().splitlines()
    assert "├── health: The `health` module: liveness and readiness probes." in lines
    health = lines.index("├── health: The `health` module: liveness and readiness probes.")
    assert lines[health + 1 : health + 4] == [
        "│   └── routes",
        "│       ├── GET /api/health",
        "│       └── GET /api/ready",
    ]
    assert "│   ├── commands" in lines
    assert (
        "│   │   ├── docs: write the reference pages of the commands, settings, modules and tables"
        in lines
    )
    assert lines.index(
        "├── about: The `about` module: name and version of the running build."
    ) < lines.index("├── auth: Tokens for MCP clients and the owner session.")


@pytest.mark.parametrize(
    "page", ["commands.md", "config.md", "modules.md", "feature-map.md", "database-tables.md"]
)
def test_the_committed_reference_pages_are_what_docs_writes(tmp_path: Path, page: str) -> None:
    assert docs(tmp_path) == 0
    made = (tmp_path / page).read_text()
    kept = (ROOT / "docs" / "reference" / page).read_text()
    assert made == kept, (
        f"docs/reference/{page} is out of date: run `code-factory docs --out docs/reference`"
    )
