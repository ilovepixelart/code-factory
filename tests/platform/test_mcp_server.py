"""The MCP server: errors reach the model as sentences, and stdio starts up like the HTTP app."""

import logging
from datetime import timedelta

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.client import CallToolResult
from mcp.types import TextContent
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from code_factory.app import MCP_TOKEN_VARIABLE, create_mcp_server
from code_factory.auth.module import module as auth
from code_factory.auth.service import AuthService
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork
from code_factory.platform.db import schema as schema_module
from code_factory.platform.errors import (
    BadRequestError,
    CodeFactoryError,
    ConflictError,
    NotFoundError,
    SettingsError,
    UnavailableError,
)
from code_factory.platform.mcp import build_mcp
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from mcp_support import isolated_unit_of_work, owner_access

LEAK = "connection to 10.0.0.5 failed: internal detail"


class ProbeService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def data_format(self) -> int:
        async with self._uow() as session:
            row = await session.execute(text("select data_format_version from schema_info"))
            return int(row.scalar_one())


def _provide(services: Services, resources: Resources) -> None:
    services.add(ProbeService, ProbeService(resources.uow))


def _register(mcp: FastMCP, services: Services) -> None:
    @mcp.tool
    async def get_ticket() -> int:
        return await services.get(ProbeService).data_format()

    @mcp.tool
    async def update_ticket() -> str:
        raise RuntimeError(LEAK)

    for name, error in {
        "list_tickets": BadRequestError("the title is empty; pass a title"),
        "create_ticket": NotFoundError("ticket CF-9 does not exist"),
        "list_activity": ConflictError("CF-9 is already merged"),
        "post_note": UnavailableError("the database is busy"),
    }.items():
        _failing_tool(mcp, name, error)


def _failing_tool(mcp: FastMCP, name: str, error: CodeFactoryError) -> None:
    async def fail() -> str:
        raise error

    mcp.tool(fail, name=name)


def _text(result: CallToolResult) -> str:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


PROBE = Module(name="probe", provide=_provide, register_tools=_register)


@pytest.mark.parametrize(
    ("tool", "sentence"),
    [
        ("list_tickets", "the title is empty; pass a title"),
        ("create_ticket", "ticket CF-9 does not exist"),
        ("list_activity", "CF-9 is already merged"),
        ("post_note", "the database is busy"),
    ],
)
async def test_a_domain_error_reaches_the_model_as_its_sentence(tool: str, sentence: str) -> None:
    async with Client(build_mcp(Services(), [PROBE], access=owner_access())) as client:
        result = await client.call_tool(tool, {}, raise_on_error=False)
    assert result.is_error
    assert _text(result) == sentence


async def test_an_unexpected_error_reaches_the_model_as_a_generic_sentence_and_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with Client(build_mcp(Services(), [PROBE], access=owner_access())) as client:
        result = await client.call_tool("update_ticket", {}, raise_on_error=False)
    assert result.is_error
    assert _text(result) == "Error calling tool 'update_ticket'"
    assert LEAK not in str(result)
    logged = [
        r for r in caplog.records if isinstance(r.exc_info, tuple) and r.exc_info[0] is RuntimeError
    ]
    assert [r.levelno for r in logged] == [logging.ERROR]
    assert "update_ticket" in logged[0].getMessage()


async def _token(connection: AsyncConnection) -> str:
    issued = await AuthService(isolated_unit_of_work(connection)).issue_owner_token(
        "stdio test", lifetime=timedelta(hours=1)
    )
    return issued.token.get_secret_value()


async def test_the_stdio_server_runs_the_startup_so_a_tool_reaches_the_database(
    settings: Settings,
    connection: AsyncConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MCP_TOKEN_VARIABLE, await _token(connection))
    server = create_mcp_server(settings, [auth, PROBE], isolated_unit_of_work(connection).sessions)
    async with Client(server) as client:
        result = await client.call_tool("get_ticket", {})
    assert result.data == 1


async def test_the_stdio_server_refuses_a_database_it_cannot_read(
    settings: Settings,
    migrated: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MCP_TOKEN_VARIABLE, "cfo_" + "A" * 43)
    monkeypatch.setattr(schema_module, "EXPECTED_REVISION", "a_newer_revision")
    with pytest.raises(RuntimeError, match="code-factory db upgrade"):
        async with Client(create_mcp_server(settings, [auth, PROBE])):
            pytest.fail("the server started on a database it cannot read")


def test_the_stdio_server_will_not_start_without_a_token(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(MCP_TOKEN_VARIABLE, raising=False)
    with pytest.raises(SettingsError, match="CODE_FACTORY_MCP_TOKEN is not set"):
        create_mcp_server(settings, [auth, PROBE])


def test_the_stdio_server_will_not_start_on_a_blank_token(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(MCP_TOKEN_VARIABLE, "  ")
    with pytest.raises(SettingsError, match="CODE_FACTORY_MCP_TOKEN is not set"):
        create_mcp_server(settings, [auth, PROBE])
