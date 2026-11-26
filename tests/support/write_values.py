"""Values the ticket write tests share."""

import re
from typing import Any

from code_factory.tickets.models import (
    Column,
    LinkGraph,
    NewTicket,
    Ticket,
    TicketAddress,
    TicketCore,
)
from code_factory.tickets.service import TicketService
from ticket_values import NOW


def core(number: int = 1, **over: Any) -> TicketCore:  # noqa: ANN401  # any field of the ticket
    """A live ticket of repository `sample`, every field empty unless given."""
    fields: dict[str, Any] = {
        "id": f"CF-{number}",
        "number": number,
        "repository": "sample",
        "title": f"T{number}",
        "type": "feature",
        "description": "",
        "labels": [],
        "priority": "",
        "assignee": "",
        "due": "",
        "blocked": "",
        "rank": 0,
        "e2e": "",
        "tests": "",
        "budget": "",
        "parallel": "",
        "source": "",
        "steps": "",
        "pages": "",
        "parent": "",
        "blocked_by": [],
        "caused_by": [],
        "archived": False,
        "branch": "",
        "pull_request": None,
        "merged": False,
        "column": Column.SPEC,
        "created_at": NOW,
        "updated_at": NOW,
    }
    return TicketCore(**{**fields, **over})


def graph(*ids: int, parents: dict[int, int] | None = None) -> LinkGraph:
    """The live tickets `CF-<n>` and each one's parent."""
    return LinkGraph(
        ids=[f"CF-{n}" for n in ids],
        parent_of={f"CF-{c}": f"CF-{p}" for c, p in (parents or {}).items()},
    )


def no_branch_refusal(_name: str) -> str | None:
    """A branch checker that accepts every name."""
    return None


async def file(
    tickets: TicketService,
    title: str,
    repository: str = "sample",
    **fields: Any,  # noqa: ANN401  # any field of the new ticket
) -> Ticket:
    """A ticket of `repository` made through the ticket service."""
    new = NewTicket.model_validate({"repository": repository, "title": title, **fields})
    return await tickets.create(new, by="owner")


def address(ticket: Ticket | TicketCore) -> TicketAddress:
    """Where the ticket is."""
    return TicketAddress(repository=ticket.repository, id=ticket.id)


def exactly(sentence: str) -> str:
    """A `match=` pattern for a message that is exactly `sentence`."""
    return f"^{re.escape(sentence)}$"
