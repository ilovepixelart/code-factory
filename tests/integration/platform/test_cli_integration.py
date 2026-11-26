"""The command line, through `main(argv)`: exit codes, one-sentence errors, no tracebacks."""

import argparse
import sys
from functools import partial

import pytest
from sqlalchemy import text

from code_factory import app as composition_root
from code_factory.app import MCP_TOKEN_VARIABLE
from code_factory.platform import cli
from code_factory.platform.db import EXPECTED_REVISION, UnitOfWork
from code_factory.platform.db import schema as schema_module
from code_factory.platform.module import Command, Module, Resources
from code_factory.platform.services import Services


def run(*argv: str) -> int:
    return composition_root.main(list(argv))


def test_db_check_reports_a_database_at_head(
    settings: object,  # noqa: ARG001
    migrated: None,  # noqa: ARG001
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("db", "check") == 0
    assert capsys.readouterr().out == (
        f"database is at head (revision {EXPECTED_REVISION}, data format 1)\n"
    )


def test_db_check_names_the_repair_when_the_database_is_behind(
    settings: object,  # noqa: ARG001
    migrated: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(schema_module, "EXPECTED_REVISION", "a_newer_revision")
    assert run("db", "check") == 1
    assert capsys.readouterr().err == (
        f"code-factory: the database is at revision {EXPECTED_REVISION} but this build expects "
        "a_newer_revision; run `code-factory db upgrade`, or install the build that wrote the "
        "database if it is newer\n"
    )


def test_db_upgrade_on_a_migrated_database_reports_head(
    settings: object,  # noqa: ARG001
    migrated: None,  # noqa: ARG001
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("db", "upgrade") == 0
    assert capsys.readouterr().out == f"database is at head ({EXPECTED_REVISION})\n"


def _main_with(module: Module, *argv: str) -> int:
    return cli.main(
        list(argv),
        create_app=composition_root.create_app,
        create_mcp=composition_root.create_mcp_server,
        open_services=partial(composition_root.open_services, modules=[module]),
        modules=[module],
    )


def test_the_mcp_command_refuses_a_database_it_cannot_read_with_one_sentence(
    settings: object,  # noqa: ARG001
    migrated: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(MCP_TOKEN_VARIABLE, "cfo_" + "A" * 43)
    monkeypatch.setattr(schema_module, "EXPECTED_REVISION", "a_newer_revision")
    assert run("mcp") == 1
    err = capsys.readouterr().err
    assert err.startswith("code-factory: the database is at revision ")
    assert "code-factory db upgrade" in err
    assert "Traceback" not in err


class _Format:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def read(self) -> int:
        async with self._uow() as session:
            row = await session.execute(text("select data_format_version from schema_info"))
            return int(row.scalar_one())


def _services_module() -> Module:
    async def run_async(_args: argparse.Namespace, services: Services) -> int:
        sys.stdout.write(f"format {await services.get(_Format).read()}\n")
        return 0

    def provide(services: Services, resources: Resources) -> None:
        services.add(_Format, _Format(resources.uow))

    return Module(
        name="format",
        provide=provide,
        commands=(Command("format", "print the data format", run_async=run_async),),
    )


def test_a_module_command_reaches_the_database_through_its_service(
    settings: object,  # noqa: ARG001
    migrated: None,  # noqa: ARG001
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _main_with(_services_module(), "format") == 0
    assert capsys.readouterr().out == "format 1\n"


def test_a_module_command_with_services_stops_on_a_database_it_cannot_read(
    settings: object,  # noqa: ARG001
    migrated: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(schema_module, "EXPECTED_REVISION", "a_newer_revision")
    assert _main_with(_services_module(), "format") == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "code-factory db upgrade" in captured.err
