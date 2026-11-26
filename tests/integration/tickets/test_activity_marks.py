"""The marks of many tickets in one read: the last column entry, archive and activity."""

from datetime import UTC, datetime

from code_factory.tickets.models import NewActivity, Ticket
from code_factory.tickets.service import ActivityService
from ticket_values import NOW, OWNER

MOVED = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
ARCHIVED = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
EDITED = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)


async def stage(activity: ActivityService, ticket: Ticket, to: str, at: datetime) -> None:
    await activity.append(ticket.id, NewActivity(kind="stage", data={"to": to}, at=at), by=OWNER)


async def test_the_newest_move_and_archive_and_any_record_are_told_apart(
    activity: ActivityService, ticket: Ticket
) -> None:
    await stage(activity, ticket, "build", MOVED)
    await stage(activity, ticket, "review", LATER)
    await activity.append(ticket.id, NewActivity(kind="archived", at=ARCHIVED), by=OWNER)
    await activity.append(
        ticket.id, NewActivity(kind="note", data={"text": "x"}, at=EDITED), by=OWNER
    )
    marks = (await activity.latest_marks([ticket.id]))[ticket.id]
    assert (marks.moved_to, marks.moved_at) == ("review", LATER)
    assert marks.archived_at == ARCHIVED
    assert marks.last_at == EDITED


async def test_a_ticket_never_moved_or_archived_has_only_its_creation(
    activity: ActivityService, ticket: Ticket
) -> None:
    marks = (await activity.latest_marks([ticket.id]))[ticket.id]
    assert (marks.moved_to, marks.moved_at, marks.archived_at) == ("", None, None)
    assert marks.last_at == NOW


async def test_each_ticket_has_its_own_marks(activity: ActivityService, ticket: Ticket) -> None:
    await stage(activity, ticket, "build", MOVED)
    other = await activity.latest_marks([ticket.id, "CF-999999"])
    assert set(other) == {ticket.id}
    assert other[ticket.id].moved_at == MOVED


async def test_no_ticket_asked_is_no_marks(activity: ActivityService) -> None:
    assert await activity.latest_marks([]) == {}
