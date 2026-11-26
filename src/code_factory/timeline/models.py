"""What the timeline hands out: a page of feed entries."""

from pydantic import BaseModel

from code_factory.tickets.models import ActivityEntry


class TimelinePage(BaseModel):
    """A page of a ticket's merged feed; `next_cursor` continues it, `None` at its end."""

    items: list[ActivityEntry]
    next_cursor: str | None
