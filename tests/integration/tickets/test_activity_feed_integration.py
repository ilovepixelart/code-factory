"""The merged activity feed: one entry model, a sentence for each record this module writes, and
the merge of feeds that other modules contribute (talk, delivery, checks).

Sentences are worked by hand from the record keys the previous implementation wrote.
"""

from code_factory.tickets.models import NewActivity, Ticket
from code_factory.tickets.service import ActivityService
from ticket_values import OWNER


async def test_a_tickets_records_become_entries_of_its_own_source(
    activity: ActivityService, ticket: Ticket
) -> None:
    await activity.append(ticket.id, NewActivity(kind="run.started", data={}), by="board")
    entries = await activity.entries(ticket.id)
    assert [(e.kind, e.by, e.sentence, e.source) for e in entries] == [
        ("created", OWNER, "Created as a feature", "tickets"),
        ("run.started", "board", "Run started", "tickets"),
    ]
