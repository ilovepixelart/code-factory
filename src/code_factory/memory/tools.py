"""The memory tools: read the owner's standing rules and lessons, propose a new lesson."""

from typing import Annotated

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from code_factory.memory.models import (
    MemoryEntry,
    MemoryFilter,
    MemoryKind,
    MemoryStatus,
    NewMemory,
)
from code_factory.memory.service import MemoryService
from code_factory.platform.errors import BadRequestError, ForbiddenError
from code_factory.platform.identity import Role
from code_factory.platform.mcp import current_actor, policy
from code_factory.platform.mcp.hints import APPENDS, READ_ONLY
from code_factory.platform.mcp.quota import quota_lock
from code_factory.platform.mcp.results import Page, PageLimit, page_after
from code_factory.platform.services import Services

TEXT_LIMIT = 1500  # characters of a statement or a reason a list carries


class MemoryRow(BaseModel):
    """An entry in a search: what to do, why, and what guards it."""

    repository: str
    id: str
    kind: MemoryKind
    statement: str
    why: str
    guard: str
    scope: str
    cites: list[str]
    status: MemoryStatus
    stale: bool
    truncated: bool = False


class Proposed(BaseModel):
    """A proposal that was recorded: it is held until the owner approves it."""

    id: str
    repository: str
    status: MemoryStatus


def _row(entry: MemoryEntry) -> MemoryRow:
    cut = len(entry.statement) > TEXT_LIMIT or len(entry.why) > TEXT_LIMIT
    return MemoryRow(
        repository=entry.repository,
        id=entry.id,
        kind=entry.kind,
        statement=entry.statement[:TEXT_LIMIT],
        why=entry.why[:TEXT_LIMIT],
        guard=entry.guard,
        scope=entry.scope,
        cites=entry.cites,
        status=entry.status,
        stale=entry.stale,
        truncated=cut,
    )


def register_tools(mcp: FastMCP, services: Services) -> None:
    """Add the memory tools to `mcp`."""
    memory = services.get(MemoryService)

    @mcp.tool(annotations=READ_ONLY)
    async def search_memory(
        query: Annotated[
            str, Field(description="Words that must all match; empty lists all.")
        ] = "",
        kinds: list[MemoryKind] | None = None,
        status: Annotated[
            MemoryStatus, Field(description="Runs read active entries only.")
        ] = "active",
        repository: Annotated[str | None, Field(description="Default: the caller's own.")] = None,
        limit: PageLimit = 10,
        cursor: Annotated[str | None, Field(description="next_cursor of the last page.")] = None,
    ) -> Page[MemoryRow]:
        """Search the owner's standing rules, decisions and lessons; every word of the query must match and an empty query lists them all. Use before asking or acting on a guess, to learn what is already decided; to record a lesson use propose_memory."""  # noqa: E501
        actor = current_actor()
        if actor.role is not Role.OWNER and status != "active":
            msg = "forbidden: a run reads active memory only. Leave status as it is."
            raise ForbiddenError(msg)
        where = MemoryFilter(
            repository=policy.scope_repository(actor, repository), kinds=kinds, status=status
        )
        rows = [_row(entry) for entry in await memory.search(query, where)]
        return page_after(rows, limit, cursor, lambda row: f"{row.repository}:{row.id}")

    @mcp.tool(annotations=APPENDS)
    async def propose_memory(
        statement: Annotated[str, Field(description="What to do now.")],
        kind: MemoryKind = "lesson",
        why: Annotated[str, Field(description="What went wrong.")] = "",
        guard: Annotated[str, Field(description="The test that now prevents it, if any.")] = "",
        cites: Annotated[list[str] | None, Field(description="Paths or test names.")] = None,
        scope: Annotated[str, Field(description="Who loads it; empty loads for everyone.")] = "",
        supersedes: Annotated[list[str] | None, Field(description="Entry ids it replaces.")] = None,
        repository: Annotated[str | None, Field(description="Default: the caller's own.")] = None,
    ) -> Proposed:
        """Propose a lesson: what to do now, why (what went wrong), the guard that now prevents it and the paths or tests it is about. It is held until the owner approves it. Use when a mistake that could recur has been fixed; search_memory finds what exists."""  # noqa: E501
        actor = current_actor()
        repository = policy.scope_repository(actor, repository)
        if repository is None:
            msg = "repository is required: name the tracked repository the lesson belongs to"
            raise BadRequestError(msg)
        new = NewMemory(
            repository=repository,
            kind=kind,
            statement=statement,
            why=why,
            guard=guard,
            cites=cites or [],
            scope=scope,
            supersedes=supersedes or [],
        )
        async with quota_lock(actor.subject):
            if actor.role is not Role.OWNER:
                used = await memory.count_proposed_by(actor.subject)
                policy.check_quota(actor, "memory_proposals", used=used)
            entry = await memory.propose(new, by=actor.subject)
        return Proposed(id=entry.id, repository=entry.repository, status=entry.status)
