"""An MCP access for tests that need a server but not the auth service."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastmcp import Client
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from code_factory.platform.db import UnitOfWork
from code_factory.platform.identity import Actor, Role
from code_factory.platform.mcp import Access, build_mcp
from code_factory.platform.module import Module
from code_factory.platform.services import Services

OWNER = Actor(
    role=Role.OWNER,
    subject="owner:test",
    token_id=1,
    expires_at=datetime(2999, 1, 1, tzinfo=UTC),
)


class NoTokens:
    """A verifier that knows no token: only a fixed actor gets in."""

    async def verify_token(self, token: str) -> Actor | None:  # noqa: ARG002
        return None


def owner_access() -> Access:
    """In-process access as the owner."""
    return Access(verifier=NoTokens(), actor=OWNER)


class Isolated(UnitOfWork):
    """A unit of work on the test's rolled-back connection, as the `app` fixture builds."""

    def __init__(self, connection: AsyncConnection) -> None:
        self.sessions = async_sessionmaker(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        super().__init__(self.sessions)


def isolated_unit_of_work(connection: AsyncConnection) -> Isolated:
    """The unit of work and its session factory for `connection`."""
    return Isolated(connection)


def run_actor(stage: str, ticket_id: str | None, run_id: str = "r1") -> Actor:
    """A run's identity on repository `sample`; no ticket makes it a coordinator."""
    role = Role.RUN if ticket_id is not None else Role.COORDINATOR
    return Actor(
        role=role,
        subject=f"run:{run_id}",
        token_id=7,
        run_id=run_id,
        ticket_id=ticket_id,
        stage=stage,
        repository="sample",
        expires_at=datetime(2999, 1, 1, tzinfo=UTC),
    )


class Called:
    """What a tool call answered: the structured content, or the error text."""

    def __init__(self, ok: bool, data: dict[str, Any], text: str) -> None:
        self.ok, self.data, self.text = ok, data, text


async def call(
    services: Services, modules: Sequence[Module], actor: Actor, tool: str, **arguments: object
) -> Called:
    """Call `tool` as `actor` on a server over `services`, through the in-memory client."""
    server = build_mcp(services, modules, access=Access(verifier=NoTokens(), actor=actor))
    async with Client(server) as client:
        result = await client.call_tool(tool, arguments, raise_on_error=False)
    text = result.content[0].text if result.content and hasattr(result.content[0], "text") else ""
    return Called(not result.is_error, result.structured_content or {}, text)
