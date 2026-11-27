"""get_ticket, list_tickets, create_ticket, update_ticket."""

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from code_factory.platform.errors import BadRequestError, ForbiddenError
from code_factory.platform.identity import Actor, Role
from code_factory.platform.mcp import current_actor, policy
from code_factory.platform.mcp.hints import APPENDS, READ_ONLY, SETS
from code_factory.platform.mcp.quota import quota_lock
from code_factory.platform.mcp.results import Page, PageLimit, page_after
from code_factory.platform.mcp.scope import scope_ticket
from code_factory.platform.services import Services
from code_factory.tickets.models import (
    Column,
    NewTicket,
    Priority,
    Ticket,
    TicketFields,
    TicketFilter,
    TicketType,
)
from code_factory.tickets.rules import check_branch
from code_factory.tickets.service import ActivityService, TicketService
from code_factory.tickets.tools.shapes import (
    DESCRIPTION_LIMIT,
    Created,
    TicketResult,
    TicketRow,
    Updated,
)

TicketId = Annotated[
    str | None,
    Field(description="The ticket, such as CF-12. A run may leave it out: it has one ticket."),
]


def _row(ticket: Ticket) -> TicketRow:
    return TicketRow(
        id=ticket.id,
        title=ticket.title,
        type=ticket.type,
        column=ticket.column,
        priority=ticket.priority,
        labels=ticket.labels,
        assignee=ticket.assignee,
        blocked=ticket.blocked,
        parent=ticket.parent,
        branch=ticket.branch,
        archived=ticket.archived,
        updated_at=ticket.updated_at,
    )


def _lineage(actor: Actor, parent: str | None) -> tuple[str | None, list[str]]:
    """The parent a new ticket gets and the tickets that caused it, by who files it."""
    if actor.role is not Role.RUN:
        return parent, []
    if actor.stage == "split":
        return actor.ticket_id, []
    if parent is not None:
        msg = "forbidden: only a split run, a coordinator or the owner may set parent."
        raise ForbiddenError(msg)
    return parent, [] if actor.ticket_id is None else [actor.ticket_id]


async def _set_branch(
    tickets: TicketService, ticket_id: str, held: str | None, branch: str | None, actor: Actor
) -> bool:
    """Set the branch, or clear it when empty; whether it changed."""
    if branch is None or branch == held:
        return False
    if branch:
        await tickets.set_branch(ticket_id, branch, by=actor.subject)
    else:
        await tickets.clear_branch(ticket_id, by=actor.subject)
    return True


async def _set_archived(
    tickets: TicketService, ticket_id: str, held: bool, archived: bool | None, actor: Actor
) -> bool:
    """Archive or unarchive; whether it changed."""
    if archived is None or archived == held:
        return False
    if archived:
        await tickets.archive(ticket_id, by=actor.subject)
    else:
        await tickets.unarchive(ticket_id, by=actor.subject)
    return True


def register(mcp: FastMCP, services: Services) -> None:
    """Add the ticket tools to `mcp`."""
    tickets = services.get(TicketService)
    _register_reads(mcp, tickets)
    _register_writes(mcp, tickets, services.get(ActivityService))


def _register_reads(mcp: FastMCP, tickets: TicketService) -> None:

    @mcp.tool(annotations=READ_ONLY)
    async def get_ticket(ticket_id: TicketId = None) -> TicketResult:
        """Read a ticket's fields, state, its documents' names and versions and its latest activity, without document text. Use when starting work or judging one ticket; for a document's text use read_document, for older history list_activity."""  # noqa: E501
        actor = current_actor()
        ticket = await scope_ticket(actor, ticket_id, tickets)
        view = await tickets.get_view(ticket)
        description = view.ticket.description
        cut = len(description) > DESCRIPTION_LIMIT
        shown = view.ticket.model_copy(update={"description": description[:DESCRIPTION_LIMIT]})
        return TicketResult(
            ticket=shown,
            documents=view.documents,
            recent_activity=view.recent_activity,
            description_truncated=cut,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def list_tickets(
        column: Column | None = None,
        label: str | None = None,
        parent: Annotated[
            str | None, Field(description="Only the children of this ticket.")
        ] = None,
        repository: Annotated[str | None, Field(description="Default: the caller's own.")] = None,
        include_archived: bool = False,
        limit: PageLimit = 25,
        cursor: Annotated[str | None, Field(description="next_cursor of the last page.")] = None,
    ) -> Page[TicketRow]:
        """List tickets in board order with column, priority, labels, blocked state and branch, filtered by column, label, parent or repository. Use to decide what to work on or find a ticket; for one ticket's detail use get_ticket."""  # noqa: E501
        actor = current_actor()
        where = TicketFilter(
            repository=policy.scope_repository(actor, repository),
            column=column,
            label=label,
            parent=parent,
            archived=None if include_archived else False,
        )
        found = [_row(ticket) for ticket in await tickets.list(where)]
        return page_after(found, limit, cursor, lambda row: row.id)


def _register_writes(mcp: FastMCP, tickets: TicketService, activity: ActivityService) -> None:
    @mcp.tool(annotations=APPENDS)
    async def create_ticket(
        title: str,
        type: TicketType = "feature",  # noqa: A002  # the field is called type on the ticket
        description: str = "",
        labels: list[str] | None = None,
        priority: Priority = "",
        blocked_by: Annotated[list[str] | None, Field(description="Ticket ids.")] = None,
        parent: Annotated[str | None, Field(description="Owner and coordinator only.")] = None,
        repository: Annotated[str | None, Field(description="Default: the caller's own.")] = None,
    ) -> Created:
        """Create a ticket under the next number. A run files a follow-up for something found on the way (a few per run); the owner files any ticket. Use when new work should go on the board; for an existing ticket use update_ticket."""  # noqa: E501
        actor = current_actor()
        repository = policy.scope_repository(actor, repository)
        if repository is None:
            msg = "repository is required: name the tracked repository the ticket belongs to"
            raise BadRequestError(msg)
        parent, caused_by = _lineage(actor, parent)
        new = NewTicket(
            repository=repository,
            title=title,
            type=type,
            description=description,
            labels=labels or [],
            priority=priority,
            blocked_by=blocked_by or [],
            parent=parent,
            caused_by=caused_by,
        )
        async with quota_lock(actor.subject):
            if actor.role is not Role.OWNER:
                used = await activity.count_authored(actor.subject, "created")
                policy.check_quota(actor, "follow_up_tickets", used=used)
            made = await tickets.create(new, by=actor.subject)
        return Created(id=made.id, column=made.column)

    @mcp.tool(annotations=SETS)
    async def update_ticket(
        ticket_id: str,
        fields: Annotated[
            TicketFields | None, Field(description="Only fields named change.")
        ] = None,
        branch: Annotated[
            str | None, Field(description="Set it; an empty string clears it.")
        ] = None,
        archived: Annotated[bool | None, Field(description="Archive or unarchive.")] = None,
    ) -> Updated:
        """Change named fields of a ticket (title, type, description, labels, priority, assignee, due, blocked, rank, tests, links), its branch, or archive it, checked as the board checks them and recorded in its activity. Use when a ticket's card should say something else; the column follows the branch and pull request."""  # noqa: E501
        actor = current_actor()
        if branch is not None and branch != "":
            check_branch(branch)  # before anything is written: the edit is all or nothing
        edited = await tickets.update(ticket_id, fields or TicketFields(), by=actor.subject)
        changed = list(edited.changed)
        if await _set_branch(tickets, ticket_id, edited.ticket.branch, branch, actor):
            changed.append("branch")
        if await _set_archived(tickets, ticket_id, edited.ticket.archived, archived, actor):
            changed.append("archived")
        return Updated(id=edited.ticket.id, changed=changed)
