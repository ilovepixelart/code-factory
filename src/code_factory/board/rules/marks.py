"""The times a ticket's history gives: when it entered its column and when it left the board."""

from datetime import datetime

from code_factory.tickets.models import ActivityMarks, Ticket


def entered_column(ticket: Ticket, marks: ActivityMarks | None) -> datetime:
    """The newest move into the ticket's column; its creation when it never moved there."""
    if marks and marks.moved_at and marks.moved_to == ticket.column.value:
        return marks.moved_at
    return ticket.created_at


def left_board(published: datetime | None, marks: ActivityMarks | None) -> float:
    """The release publish time, else the last `archived` record, else the last record, else 0."""
    moment = published or (marks.archived_at or marks.last_at if marks else None)
    return moment.timestamp() if moment else 0.0
