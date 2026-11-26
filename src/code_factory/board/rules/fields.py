"""A ticket's fields and questions as the ticket page lists them."""

from datetime import datetime
from typing import Any

from code_factory.platform.text import stamp
from code_factory.tickets.models import Ticket


def ticket_fields(ticket: Ticket, stage_since: datetime, declared: str) -> dict[str, Any]:
    """The editable fields as the form reads them: lists as comma-joined text.

    `stage` is the stage the ticket declares (empty when none); `stage_since` is when the ticket
    entered its column.
    """
    return {
        "id": ticket.id,
        "title": ticket.title,
        "type": ticket.type,
        "branch": ticket.branch,
        "e2e": ticket.e2e,
        "tests": ticket.tests,
        "description": ticket.description,
        "stage": declared,
        "labels": ", ".join(ticket.labels),
        "priority": ticket.priority,
        "assignee": ticket.assignee,
        "due": ticket.due,
        "blocked": ticket.blocked,
        "archived": ticket.archived,
        "rank": ticket.rank,
        "stage_since": stamp(stage_since),
        "blocked_by": ", ".join(ticket.blocked_by),
        "caused_by": ", ".join(ticket.caused_by),
        "parent": ticket.parent,
        "budget": ticket.budget,
        "parallel": ticket.parallel,
        "source": ticket.source,
        "steps": ticket.steps,
        "pages": ticket.pages,
    }
