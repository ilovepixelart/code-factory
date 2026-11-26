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
from code_factory.platform.config import DATABASE_URL_VARIABLE
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


def test_a_run_command_gets_the_root_parser_to_describe_every_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run(args: argparse.Namespace) -> int:
        sys.stdout.write(args.root_parser.format_help())
        return 0

    assert (
        _main(Module(name="docs", commands=(Command("docs", "write docs", run=run),)), "docs") == 0
    )
    out = capsys.readouterr().out
    assert out.startswith("usage: code-factory ")
    assert "write docs" in out


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


def test_command_services_without_a_database_builds_services_with_no_url_set(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(DATABASE_URL_VARIABLE, raising=False)
    monkeypatch.chdir("/")

    def run(args: argparse.Namespace) -> int:
        async def names() -> str:
            async with command_services(args, database=False) as services:
                return type(services.get(Format)).__name__

        sys.stdout.write(f"{asyncio.run(names())}\n")
        return 0

    module = Module(name="f", provide=_provide, commands=(Command("f", "x", run=run),))
    assert _main(module, "f") == 0
    assert capsys.readouterr().out == "Format\n"


def test_a_service_that_uses_the_database_in_a_database_free_command_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(DATABASE_URL_VARIABLE, raising=False)
    monkeypatch.chdir("/")
    assert _main(_reading_module(database=False), "format") == 1
    assert capsys.readouterr().err == (
        "code-factory: this command runs without a database, so it cannot read or write one\n"
    )


def test_a_database_free_command_still_runs_the_stop_hooks_its_services_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DATABASE_URL_VARIABLE, raising=False)
    monkeypatch.chdir("/")
    stopped: list[str] = []

    def provide(_services: Services, resources: Resources) -> None:
        async def close() -> None:
            stopped.append("closed")

        resources.on_stop.append(close)

    def run(args: argparse.Namespace) -> int:
        async def use() -> None:
            async with command_services(args, database=False):
                assert stopped == []

        asyncio.run(use())
        return 0

    module = Module(name="f", provide=provide, commands=(Command("f", "x", run=run),))
    assert _main(module, "f") == 0
    assert stopped == ["closed"]
