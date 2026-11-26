"""`code-factory config check|show`, `docs --out` and `intake-key list|revoke`, through the real
command line for what needs no database and through the command's runner for the rest."""

import argparse
import json
from pathlib import Path

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.settings.module import module
from code_factory.settings.service import SettingsService
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
