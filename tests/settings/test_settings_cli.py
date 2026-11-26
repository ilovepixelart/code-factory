"""`code-factory config check|show`, `docs --out` and `intake-key list|revoke`, through the real
command line for what needs no database and through the command's runner for the rest."""

import argparse
import json
from pathlib import Path

import pytest

from code_factory import app as composition_root
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.settings.module import module
from code_factory.settings.service import SettingsService
from repo_files import ROOT
from settings_support import arepository, write

CONFIG = ".code-factory/config.toml"
BAD_CONFIG = '[checks]\ncommand = "true"\ntimeout = "ten"\n'


def command(name: str) -> Command:
    (found,) = (c for c in module.commands if c.name == name)
    return found


async def run(
    uow: UnitOfWork, name: str, *argv: str, service: SettingsService | None = None
) -> tuple[int, SettingsService]:
    service = service or SettingsService(uow)
    services = Services()
    services.add(SettingsService, service)
    parser = argparse.ArgumentParser(prog=name)
    command(name).configure(parser)
    run_async = command(name).run_async
    assert run_async is not None
    return await run_async(parser.parse_args(argv), services), service


async def test_check_prints_each_problem_and_exits_1(
    uow: UnitOfWork, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, CONFIG, BAD_CONFIG)
    code, _ = await run(uow, "config", "check", str(tmp_path))
    captured = capsys.readouterr()
    assert code == 1
    assert (
        captured.out == ".code-factory/config.toml:3: checks.timeout: expected a positive integer\n"
    )


async def test_check_of_a_clean_repository_prints_nothing_and_exits_0(
    uow: UnitOfWork, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, CONFIG, '[checks]\ncommand = "true"\n')
    code, _ = await run(uow, "config", "check", str(tmp_path))
    assert (code, capsys.readouterr().out) == (0, "")


async def test_check_finds_the_repository_root_from_a_folder_inside_it(
    uow: UnitOfWork, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = await arepository(tmp_path / "r", {"src/a.py": ""})
    write(root, CONFIG, BAD_CONFIG)
    code, _ = await run(uow, "config", "check", str(root / "src"))
    assert (code, "checks.timeout" in capsys.readouterr().out) == (1, True)


async def test_check_prints_notes_and_the_unchecked_on_stderr(
    uow: UnitOfWork, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, CONFIG, '[checks]\ncommand = "true"\n')
    code, _ = await run(uow, "config", "check", str(tmp_path))
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == "not checked: ticket references (the tickets module is not bound)\n"


async def test_show_prints_the_effective_config_as_json_with_unset_keys_left_out(
    uow: UnitOfWork, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, CONFIG, '[agents]\nslots = 0\nretries = 3\n[[recurring]]\ntitle = "t"\n')
    code, _ = await run(uow, "config", "show", str(tmp_path))
    assert code == 0
    assert json.loads(capsys.readouterr().out) == {
        "agents": {"retries": 3},
        "recurring": [{"title": "t"}],
    }


async def test_intake_key_list_and_revoke(
    uow: UnitOfWork, capsys: pytest.CaptureFixture[str]
) -> None:
    service = SettingsService(uow)
    await service.grant_intake_key(
        "CODE_FACTORY_INTAKE_JIRA", Path("/r"), "https://acme.atlassian.net"
    )
    code, _ = await run(uow, "intake-key", "list", service=service)
    out = capsys.readouterr().out.splitlines()
    assert code == 0
    assert out[0].split() == ["KEY", "REPOSITORY", "URL"]
    assert out[1].split() == ["CODE_FACTORY_INTAKE_JIRA", "/r", "https://acme.atlassian.net"]
    code, _ = await run(uow, "intake-key", "revoke", "CODE_FACTORY_INTAKE_JIRA", service=service)
    assert (code, capsys.readouterr().out) == (0, "revoked CODE_FACTORY_INTAKE_JIRA\n")
    assert await service.list_intake_grants() == []


async def test_revoking_what_is_not_held_or_without_a_name_is_a_sentence(uow: UnitOfWork) -> None:
    with pytest.raises(NotFoundError, match="no grant for CODE_FACTORY_INTAKE_X"):
        await run(uow, "intake-key", "revoke", "CODE_FACTORY_INTAKE_X")
    with pytest.raises(BadRequestError, match="revoke needs the key name"):
        await run(uow, "intake-key", "revoke")


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
