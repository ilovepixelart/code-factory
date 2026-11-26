"""What the ticket services share."""

from datetime import UTC, datetime

from code_factory.platform.errors import NotFoundError
from code_factory.tickets.models import PullRequest, Ticket
from code_factory.tickets.repository import Links
from code_factory.tickets.rules import column_of, ticket_id
from code_factory.tickets.tables import TicketRow


def utc_now() -> datetime:
    """The services' default clock."""
    return datetime.now(UTC)


def not_found(number: int) -> NotFoundError:
    """The sentence for a ticket that does not exist."""
    return NotFoundError(f"{ticket_id(number)} does not exist; list the tickets to find its id")


_ROW_FIELDS = (
    "number",
    "repository",
    "title",
    "type",
    "description",
    "labels",
    "priority",
    "assignee",
    "due",
    "blocked",
    "rank",
    "e2e",
    "tests",
    "budget",
    "parallel",
    "source",
    "steps",
    "pages",
    "archived",
    "branch",
    "merged",
    "created_at",
    "updated_at",
)


def to_ticket(row: TicketRow, links: Links, pull: PullRequest | None) -> Ticket:
    """A ticket's answer, its column read from its facts."""
    parent = links.get("parent", [])
    return Ticket(
        id=ticket_id(row.number),
        parent=ticket_id(parent[0]) if parent else "",
        blocked_by=[ticket_id(n) for n in links.get("blocked_by", [])],
        caused_by=[ticket_id(n) for n in links.get("caused_by", [])],
        pull_request=pull,
        column=column_of(row.branch, pull.state if pull else None, row.merged),
        **{name: getattr(row, name) for name in _ROW_FIELDS},
    )
