"""The MCP server: errors reach the model as sentences, and stdio starts up like the HTTP app."""

import logging

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.client import CallToolResult
from mcp.types import TextContent
from sqlalchemy import text

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import (
    BadRequestError,
    CodeFactoryError,
    ConflictError,
    NotFoundError,
    UnavailableError,
)
from code_factory.platform.mcp import build_mcp
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from mcp_support import owner_access

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
