"""A ticket's history: its records, their pages, the feed entries and diagnoses."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class NewActivity(BaseModel):
    """An activity record to append. `at` defaults to the service's clock."""

    kind: str
    data: dict[str, Any] = Field(default_factory=dict)
    at: datetime | None = None


class Activity(BaseModel):
    """One appended record of a ticket's history; `id` rises with every append."""

    id: int
    ticket_id: str
    at: datetime
    kind: str
    by: str
    data: dict[str, Any]


class ActivityPage(BaseModel):
    """A page of a ticket's history; `next_cursor` continues it, `None` at its end."""

    items: list[Activity]
    next_cursor: str | None


NoteKind = Literal["note", "diagnosis"]


class Diagnosis(BaseModel):
    """A diagnosis posted on a ticket: who wrote it, what it says and when."""

    ticket_id: str
    author: str
    text: str
    at: datetime


class ActivityEntry(BaseModel):
    """One line of a ticket's merged feed, whichever module's record it came from.

    `source` names the module (`tickets`, `talk`, `delivery`, `checks`); `sentence` is the line
    in plain words; `data` is the record's own keys; `id` is the record's id in its own module,
    when it has one.
    """

    at: datetime
    kind: str
    by: str
    sentence: str
    data: dict[str, Any] = Field(default_factory=dict)
    source: str = "tickets"
    id: int | None = None


class ActivityMarks(BaseModel):
    """What a ticket's history says about when it last moved, left the board and was touched.

    `moved_to` and `moved_at` are the newest `stage` record; `archived_at` the newest `archived`
    record; `last_at` the newest record of any kind. A mark with no record is empty or None.
    """

    moved_to: str = ""
    moved_at: datetime | None = None
    archived_at: datetime | None = None
    last_at: datetime | None = None
