"""Values the board tests share: a ticket with every field set."""

from datetime import UTC, datetime

from code_factory.tickets.models import Ticket

NOW = datetime(2026, 11, 23, tzinfo=UTC)


def ticket(ticket_id: str, **more: object) -> Ticket:
    values: dict[str, object] = {
        "id": ticket_id,
        "number": int(ticket_id.split("-")[1]),
        "repository": "sample",
        "title": ticket_id,
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
        "column": "spec",
        "created_at": NOW,
        "updated_at": NOW,
    }
    return Ticket(**(values | more))  # ty: ignore[invalid-argument-type]
