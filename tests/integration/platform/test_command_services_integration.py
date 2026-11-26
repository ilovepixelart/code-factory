"""What a `Command.run` can reach: the root parser and, through `command_services`, the services."""

import argparse
import asyncio
import sys
from functools import partial

import pytest
from sqlalchemy import text

from code_factory import app as composition_root
from code_factory.platform import cli
from code_factory.platform.commands import command_services
from code_factory.platform.db import UnitOfWork
from code_factory.platform.db import schema as schema_module
from code_factory.platform.module import Command, Module, Resources
from code_factory.platform.services import Services


class Format:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def read(self) -> int:
        async with self._uow() as session:
            row = await session.execute(text("select data_format_version from schema_info"))
            return int(row.scalar_one())


def _provide(services: Services, resources: Resources) -> None:
    services.add(Format, Format(resources.uow))


def _main(module: Module, *argv: str) -> int:
    return cli.main(
        list(argv),
        create_app=composition_root.create_app,
        create_mcp=composition_root.create_mcp_server,
        open_services=partial(composition_root.open_services, modules=[module]),
        modules=[module],
    )


def _reading_module(*, database: bool) -> Module:
    def run(args: argparse.Namespace) -> int:
        async def read() -> int:
            async with command_services(args, database=database) as services:
                return await services.get(Format).read()

        sys.stdout.write(f"format {asyncio.run(read())}\n")
        return 0

    return Module(name="format", provide=_provide, commands=(Command("format", "x", run=run),))


def test_command_services_gives_a_run_command_the_services_on_a_checked_database(
    settings: object,  # noqa: ARG001
    migrated: None,  # noqa: ARG001
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _main(_reading_module(database=True), "format") == 0
    assert capsys.readouterr().out == "format 1\n"


def test_command_services_with_a_database_refuses_one_the_build_cannot_read(
    settings: object,  # noqa: ARG001
    migrated: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(schema_module, "EXPECTED_REVISION", "a_newer_revision")
    assert _main(_reading_module(database=True), "format") == 1
    assert "code-factory db upgrade" in capsys.readouterr().err
