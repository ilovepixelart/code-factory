"""The guard in front of every tool: the same on stdio, in memory and over HTTP."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from mcp.shared.exceptions import MCPError

from code_factory.platform.errors import UnavailableError
from code_factory.platform.identity import Actor, Role
from code_factory.platform.mcp import build_mcp
from code_factory.platform.mcp.access import Access, current_actor
from code_factory.platform.module import Module
from code_factory.platform.services import Services

EXPIRES = datetime(2026, 12, 1, tzinfo=UTC)
BUILD = Actor(
    role=Role.RUN, subject="run:r1", token_id=1, run_id="r1", ticket_id="CF-12", stage="build",
    repository="/r", expires_at=EXPIRES,
)  # fmt: skip
OWNER = Actor(role=Role.OWNER, subject="owner:alex", token_id=2, expires_at=EXPIRES)


class FakeVerifier:
    """Stands in for the auth service: a token is live while it is in `live`."""

    def __init__(self, live: dict[str, Actor]) -> None:
        self.live = live

    async def verify_token(self, token: str) -> Actor | None:
        return self.live.get(token)


def _register(mcp: FastMCP, _services: Services) -> None:
    @mcp.tool
    async def get_ticket() -> str:
        return current_actor().subject

    @mcp.tool
    async def update_ticket() -> str:
        return "updated"

    @mcp.tool
    async def not_in_the_table() -> str:
        return "unreachable"


PROBE = Module(name="probe", register_tools=_register)


def _server(access: Access) -> FastMCP:
    return build_mcp(Services(), [PROBE], access=access)


def _fixed(actor: Actor) -> FastMCP:
    return _server(Access(verifier=FakeVerifier({}), actor=actor))


async def _names(server: FastMCP) -> list[str]:
    async with Client(server) as client:
        return [tool.name for tool in await client.list_tools()]


async def test_a_build_run_lists_only_the_tools_a_build_run_may_call() -> None:
    assert await _names(_fixed(BUILD)) == ["whoami", "get_ticket"]


async def test_the_owner_lists_the_tools_the_table_allows_and_never_one_outside_it() -> None:
    assert await _names(_fixed(OWNER)) == ["whoami", "get_ticket", "update_ticket"]


async def test_a_tool_the_run_may_not_call_is_refused_by_name_with_what_to_do() -> None:
    async with Client(_fixed(BUILD)) as client:
        with pytest.raises(ToolError) as refused:
            await client.call_tool("update_ticket", {})
    assert str(refused.value) == (
        "forbidden: update_ticket is not available to a build run. whoami says what is."
    )


async def test_a_tool_missing_from_the_table_is_refused_to_the_owner_too() -> None:
    async with Client(_fixed(OWNER)) as client:
        with pytest.raises(ToolError, match="forbidden: not_in_the_table is not available"):
            await client.call_tool("not_in_the_table", {})


async def test_a_tool_reads_the_actor_the_guard_resolved() -> None:
    async with Client(_fixed(BUILD)) as client:
        result = await client.call_tool("get_ticket", {})
    assert result.structured_content == {"result": "run:r1"}


async def test_whoami_describes_the_caller_and_what_it_may_do() -> None:
    async with Client(_fixed(BUILD)) as client:
        result = await client.call_tool("whoami", {})
    answer: dict[str, Any] = result.structured_content or {}
    assert (answer["role"], answer["subject"], answer["ticket_id"], answer["stage"]) == (
        "run",
        "run:r1",
        "CF-12",
        "build",
    )
    assert answer["writable_documents"] == ["notes"]
    assert answer["limits"] == {"follow_up_tickets": 3, "memory_proposals": 5}
    assert answer["tools"] == await _names(_fixed(BUILD))


async def test_the_owner_may_write_every_document_and_has_no_limits() -> None:
    async with Client(_fixed(OWNER)) as client:
        result = await client.call_tool("whoami", {})
    answer: dict[str, Any] = result.structured_content or {}
    assert answer["writable_documents"] is None
    assert answer["limits"] == {"follow_up_tickets": None, "memory_proposals": None}


async def test_whoami_is_a_read_only_tool_with_all_four_hints_set() -> None:
    async with Client(_fixed(OWNER)) as client:
        tool = next(t for t in await client.list_tools() if t.name == "whoami")
    assert tool.annotations is not None
    assert (
        tool.annotations.read_only_hint,
        tool.annotations.destructive_hint,
        tool.annotations.idempotent_hint,
        tool.annotations.open_world_hint,
    ) == (True, False, True, False)


async def test_a_stdio_style_token_is_verified_on_every_call_so_a_revoked_one_stops_at_once() -> (
    None
):
    verifier = FakeVerifier({"cfr_token": BUILD})
    server = _server(Access(verifier=verifier, token="cfr_token"))  # noqa: S106
    async with Client(server) as client:
        assert (await client.call_tool("get_ticket", {})).structured_content == {"result": "run:r1"}
        verifier.live.clear()
        with pytest.raises(ToolError) as ended:
            await client.call_tool("get_ticket", {})
    assert str(ended.value) == (
        "forbidden: this token has ended. Start a new run, or ask the owner for a new token."
    )


async def test_a_listing_with_an_ended_token_is_refused_too() -> None:
    server = _server(Access(verifier=FakeVerifier({}), token="cfr_gone"))  # noqa: S106
    async with Client(server) as client:
        with pytest.raises(MCPError, match="this token has ended"):
            await client.list_tools()


def test_an_access_names_at_most_one_of_a_token_and_an_actor() -> None:
    verifier = FakeVerifier({})
    with pytest.raises(ValueError, match="at most one"):
        Access(verifier=verifier, token="cfr_x", actor=BUILD)  # noqa: S106


class UnreachableVerifier:
    async def verify_token(self, token: str) -> Actor | None:  # noqa: ARG002
        raise UnavailableError("the database is busy; try again in a moment")


async def test_a_database_failure_while_verifying_reaches_the_model_as_its_sentence() -> None:
    server = _server(Access(verifier=UnreachableVerifier(), token="cfr_x"))  # noqa: S106
    async with Client(server) as client:
        with pytest.raises(ToolError) as refused:
            await client.call_tool("get_ticket", {})
        assert str(refused.value) == "the database is busy; try again in a moment"
        with pytest.raises(MCPError, match="the database is busy; try again in a moment"):
            await client.list_tools()
