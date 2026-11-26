"""The records of one kind of many tickets in one read, each ticket's oldest first."""

from code_factory.tickets.models import NewActivity, NewTicket, Ticket
from code_factory.tickets.service import ActivityService, TicketService
from ticket_values import OWNER


async def note(activity: ActivityService, ticket: Ticket, kind: str, text: str) -> None:
    await activity.append(ticket.id, NewActivity(kind=kind, data={"text": text}), by=OWNER)


async def test_each_ticket_has_its_records_of_the_kind_oldest_first(
    activity: ActivityService, tickets: TicketService, ticket: Ticket
) -> None:
    other = await tickets.create(NewTicket(repository="sample", title="Other"), by=OWNER)
    quiet = await tickets.create(NewTicket(repository="sample", title="Quiet"), by=OWNER)
    await note(activity, ticket, "checks", "first")
    await note(activity, other, "checks", "theirs")
    await note(activity, ticket, "note", "not a check")
    await note(activity, ticket, "checks", "second")

    found = await activity.records_of([ticket.id, other.id, quiet.id, "CF-999999"], "checks")

    texts = {t: [r.data["text"] for r in records] for t, records in found.items()}
    assert texts == {ticket.id: ["first", "second"], other.id: ["theirs"]}


async def test_no_ticket_reads_nothing(activity: ActivityService) -> None:
    assert await activity.records_of([], "checks") == {}
