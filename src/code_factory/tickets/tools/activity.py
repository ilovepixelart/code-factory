"""list_activity and post_note."""

from typing import Annotated, get_args

from fastmcp import FastMCP
from pydantic import Field

from code_factory.platform.errors import ForbiddenError
from code_factory.platform.identity import Role
from code_factory.platform.mcp import current_actor
from code_factory.platform.mcp.hints import APPENDS, READ_ONLY
from code_factory.platform.mcp.results import PageLimit
from code_factory.platform.mcp.scope import scope_ticket
from code_factory.platform.services import Services
from code_factory.tickets.models import ActivityPage, NoteKind
from code_factory.tickets.service import ActivityService, QaHoldouts, TicketService
from code_factory.tickets.tools.shapes import NoteRecorded
from code_factory.tickets.tools.tickets import TicketId

KINDS = get_args(NoteKind)
REVIEW_ROLES = frozenset({"qa", "security", "tests"})


def register(mcp: FastMCP, services: Services) -> None:
    """Add the activity tools to `mcp`."""
    activity = services.get(ActivityService)
    repository_of = services.get(TicketService)

    @mcp.tool(annotations=READ_ONLY)
    async def list_activity(
        ticket_id: TicketId = None,
        kinds: Annotated[list[str] | None, Field(description="For example stage, note.")] = None,
        limit: PageLimit = 20,
        cursor: Annotated[str | None, Field(description="next_cursor of the last page.")] = None,
    ) -> ActivityPage:
        """List a ticket's activity newest first (moves, documents, runs, checks, answers, notes, findings), filtered by kind. Use to see what happened and why work was sent back; get_ticket has only the latest few."""  # noqa: E501
        ticket = await scope_ticket(current_actor(), ticket_id, repository_of)
        return await activity.list_activity(
            ticket, kinds=kinds, limit=limit, cursor=cursor, newest_first=True
        )

    @mcp.tool(annotations=APPENDS)
    async def post_note(
        text: Annotated[str, Field(description="At most 4000 characters.")],
        ticket_id: TicketId = None,
        kind: Annotated[
            NoteKind, Field(description="diagnosis is for the owner and coordinator.")
        ] = "note",
    ) -> NoteRecorded:
        """Record a note on a ticket's activity under your name; the owner reads it. Use to leave a finding that is not a change to any field. A diagnosis (why work is stuck) is for the owner and coordinator."""  # noqa: E501
        actor = current_actor()
        if kind == "diagnosis" and actor.role is Role.RUN:
            msg = "forbidden: a run may post notes, not diagnoses. Use kind note."
            raise ForbiddenError(msg)
        ticket = await scope_ticket(actor, ticket_id, repository_of)
        role = actor.stage if actor.role is Role.RUN and actor.stage in REVIEW_ROLES else ""
        recorded = await activity.record_note(
            ticket, text, kind, by=actor.subject, review_role=role
        )
        return NoteRecorded(id=recorded.id)

    @mcp.tool(annotations=READ_ONLY)
    async def get_qa_holdout() -> str | None:
        """Read and run the owner's private acceptance cases for your QA ticket, if supplied."""
        actor = current_actor()
        if actor.role is not Role.RUN or actor.stage != "qa":
            msg = "forbidden: private acceptance cases are available to the ticket's QA run"
            raise ForbiddenError(msg)
        ticket = await scope_ticket(actor, None, repository_of)
        return await services.get(QaHoldouts).cases(ticket)
