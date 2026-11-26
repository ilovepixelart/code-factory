"""The one tool the platform itself provides: what the caller is and may do."""

from datetime import datetime

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from code_factory.platform.identity import Role
from code_factory.platform.mcp import policy
from code_factory.platform.mcp.access import current_actor


class Identity(BaseModel):
    """What a token is and what it may do."""

    role: Role
    subject: str
    run_id: str | None
    ticket_id: str | None
    stage: str | None
    repository: str | None
    expires_at: datetime
    tools: list[str]
    writable_documents: list[str] | None  # None: every document
    limits: dict[str, int | None]  # per run; None: no limit


def register_whoami(mcp: FastMCP) -> None:
    """Add `whoami` to `mcp`."""

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def whoami() -> Identity:
        """Say which role this token holds, its ticket and stage, the tools it may call, the documents it may write and its limits. Use first when unsure what you may do; for a ticket's state use get_ticket."""  # noqa: E501
        actor = current_actor()
        return Identity(
            role=actor.role,
            subject=actor.subject,
            run_id=actor.run_id,
            ticket_id=actor.ticket_id,
            stage=actor.stage,
            repository=actor.repository,
            expires_at=actor.expires_at,
            tools=[tool.name for tool in await mcp.list_tools()],
            writable_documents=policy.writable_documents(actor),
            limits={kind: policy.quota(actor, kind) for kind in policy.QUOTA_KINDS},
        )
