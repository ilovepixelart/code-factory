"""The command line, through `main(argv)`: exit codes, one-sentence errors, no tracebacks."""

import argparse
import sys
from collections.abc import Callable
from functools import partial

import pytest
from sqlalchemy import text

from code_factory import app as composition_root
from code_factory.app import MCP_TOKEN_VARIABLE
from code_factory.platform import cli
from code_factory.platform.config import DATABASE_URL_VARIABLE, Settings
from code_factory.platform.db import EXPECTED_REVISION, UnitOfWork
from code_factory.platform.db import engine as engine_module
from code_factory.platform.db import schema as schema_module
from code_factory.platform.errors import BadRequestError, CodeFactoryError
from code_factory.platform.module import Command, Module, Resources
from code_factory.platform.services import Services
from repo_files import PROJECT_VERSION

DEAD_URL = "postgresql+asyncpg://nobody:not-a-password@127.0.0.1:1/never_connected"


def run(*argv: str) -> int:
    return composition_root.main(list(argv))


def test_version_prints_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        run("--version")
    assert raised.value.code == 0
    assert capsys.readouterr().out == f"code-factory {PROJECT_VERSION}\n"


def test_an_unknown_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        run("frobnicate")
    assert raised.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.parametrize("command", [["serve"], ["mcp"], ["db", "check"], ["db", "upgrade"]])
def test_a_missing_database_url_is_one_sentence_and_exit_1(
    command: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(DATABASE_URL_VARIABLE, raising=False)
    monkeypatch.chdir("/")
    assert run(*command) == 1
    err = capsys.readouterr().err
    assert err.startswith("code-factory: CODE_FACTORY_DATABASE_URL is not set.")
    assert "security find-generic-password" in err
    assert err.count("\n") == 1
    assert "Traceback" not in err


@pytest.mark.parametrize("command", [["serve"], ["db", "check"], ["db", "upgrade"]])
def test_an_unreachable_database_is_one_sentence_and_exit_1(
    command: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, DEAD_URL)
    assert run(*command) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith(
        "code-factory: the database at 127.0.0.1:1/never_connected is not reachable ("
    )
    assert captured.err.count("\n") == 1
    assert "not-a-password" not in captured.err
    assert "Traceback" not in captured.err


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


def _module_command(run: Callable[[argparse.Namespace], int]) -> Module:
    def configure(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("name")

    return Module(
        name="greeting", commands=(Command("greet", "say hello", run=run, configure=configure),)
    )


def _main_with(module: Module, *argv: str) -> int:
    return cli.main(
        list(argv),
        create_app=composition_root.create_app,
        create_mcp=composition_root.create_mcp_server,
        open_services=partial(composition_root.open_services, modules=[module]),
        modules=[module],
    )


def test_a_module_adds_a_subcommand_that_receives_its_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run(args: argparse.Namespace) -> int:
        sys.stdout.write(f"hello {args.name}\n")
        return 7

    assert _main_with(_module_command(run), "greet", "ada") == 7
    assert capsys.readouterr().out == "hello ada\n"


def test_a_module_command_that_raises_a_domain_error_is_one_sentence_and_exit_1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run(_args: argparse.Namespace) -> int:
        msg = "the greeting is not configured; run `code-factory greet --setup`"
        raise CodeFactoryError(msg)

    assert _main_with(_module_command(run), "greet", "ada") == 1
    assert capsys.readouterr().err == (
        "code-factory: the greeting is not configured; run `code-factory greet --setup`\n"
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


def test_a_command_check_refuses_before_any_database_is_touched(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ran = []

    async def run_async(_args: argparse.Namespace, _services: Services) -> int:
        ran.append("ran")
        return 0

    def check(_settings: Settings) -> None:
        raise BadRequestError("not against this database")

    module = Module(
        name="checked",
        commands=(Command("checked", "x", run_async=run_async, check=check),),
    )
    monkeypatch.setenv(DATABASE_URL_VARIABLE, DEAD_URL)  # nothing listens: any connection fails
    assert _main_with(module, "checked") == 1
    assert (ran, capsys.readouterr().err) == ([], "code-factory: not against this database\n")


@pytest.mark.parametrize("runners", ["neither", "both"])
def test_a_command_needs_exactly_one_runner(runners: str) -> None:
    async def run_async(_args: argparse.Namespace, _services: Services) -> int:
        return 0

    given = {"run": lambda _a: 0, "run_async": run_async} if runners == "both" else {}
    with pytest.raises(ValueError, match="exactly one of run and run_async"):
        Command("x", "x", **given)  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize("command", [["mcp"], ["serve"]])
def test_an_engine_that_cannot_be_built_is_one_sentence_and_exit_1(
    command: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        msg = "bad option in postgresql+asyncpg://code_factory:not-a-password@127.0.0.1:1/x"
        raise ValueError(msg)

    monkeypatch.setenv(DATABASE_URL_VARIABLE, DEAD_URL)
    monkeypatch.setenv(MCP_TOKEN_VARIABLE, "cfo_" + "A" * 43)
    monkeypatch.setattr(engine_module, "create_async_engine", refuse)
    assert run(*command) == 1
    err = capsys.readouterr().err
    assert err == (
        "code-factory: the database engine cannot be created from CODE_FACTORY_DATABASE_URL; "
        "check the URL and the CODE_FACTORY_DB_* settings\n"
    )


def test_a_module_option_named_run_does_not_replace_the_handler(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run(args: argparse.Namespace) -> int:
        sys.stdout.write(f"run option {args.run}\n")
        return 0

    def configure(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--run", default="none")

    module = Module(name="x", commands=(Command("go", "go", run=run, configure=configure),))
    assert _main_with(module, "go", "--run", "now") == 0
    assert capsys.readouterr().out == "run option now\n"
