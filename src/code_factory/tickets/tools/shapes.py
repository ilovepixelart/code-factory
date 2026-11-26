"""What the ticket tools answer beyond the service's own models."""

from datetime import datetime

from pydantic import BaseModel

from code_factory.tickets.models import (
    Activity,
    Column,
    DocumentInfo,
    Priority,
    Ticket,
    TicketType,
)

DESCRIPTION_LIMIT = 8000  # characters of a description `get_ticket` carries


class TicketResult(BaseModel):
    """A ticket as an agent starts on it. Document text comes from `read_document`."""

    ticket: Ticket
    documents: list[DocumentInfo]
    recent_activity: list[Activity]
    description_truncated: bool = False


class TicketRow(BaseModel):
    """A ticket in a list: enough to choose one."""

    id: str
    title: str
    type: TicketType
    column: Column
    priority: Priority
    labels: list[str]
    assignee: str
    blocked: str
    parent: str
    branch: str
    archived: bool
    updated_at: datetime


class Created(BaseModel):
    """A ticket that was created."""

    id: str
    column: Column


class Updated(BaseModel):
    """A ticket after an update and the fields that changed."""

    id: str
    changed: list[str]


class NoteRecorded(BaseModel):
    """A note that was recorded: the activity record's id."""

    id: int
