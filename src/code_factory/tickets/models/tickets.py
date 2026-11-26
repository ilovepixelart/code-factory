"""What the ticket service takes and answers.

An optional text field is the empty string when unset, as the app reads it; an optional relation
(parent, pull request) is `None`.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from code_factory.tickets.models.activity import Activity
from code_factory.tickets.models.documents import DocumentInfo

TicketType = Literal["feature", "bug", "refactor", "upgrade", "hotfix", "docs"]
Priority = Literal["", "urgent", "high", "medium", "low"]


class Column(StrEnum):
    """A board column, in the order a ticket walks them."""

    SPEC = "spec"
    BUILD = "build"
    REVIEW = "review"
    MERGED = "merged"


class PullRequestState(StrEnum):
    """The state of a ticket's pull request as the forge reports it."""

    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class PullRequest(BaseModel):
    """A ticket's pull request."""

    number: int = Field(ge=1)
    state: PullRequestState
    url: str = ""


class WrittenFields(BaseModel):
    """The fields a person or an agent writes besides the title; unset (`None`) leaves a field."""

    type: TicketType | None = None
    description: str | None = None
    labels: list[str] | None = None
    priority: Priority | None = None
    assignee: str | None = None
    due: str | None = None
    blocked: str | None = None
    rank: int | None = Field(default=None, ge=0)
    e2e: str | None = None
    tests: str | None = None
    budget: str | None = None
    parallel: str | None = None
    source: str | None = None
    steps: str | None = None
    pages: str | None = None
    parent: str | None = None
    blocked_by: list[str] | None = None
    caused_by: list[str] | None = None


class TicketFields(WrittenFields):
    """An edit: only the fields given change."""

    title: str | None = None


class NewTicket(WrittenFields):
    """A ticket to create; its number comes from the sequence."""

    repository: str
    title: str


class Ticket(BaseModel):
    """A ticket as the board shows it, with the column its facts put it in."""

    id: str
    number: int
    repository: str
    title: str
    type: TicketType
    description: str
    labels: list[str]
    priority: Priority
    assignee: str
    due: str
    blocked: str
    rank: int
    e2e: str
    tests: str
    budget: str
    parallel: str
    source: str
    steps: str
    pages: str
    parent: str
    blocked_by: list[str]
    caused_by: list[str]
    archived: bool
    branch: str
    pull_request: PullRequest | None
    merged: bool
    column: Column
    created_at: datetime
    updated_at: datetime


class Edited(BaseModel):
    """A ticket after an edit, and the names of the fields the edit changed, in field order."""

    ticket: Ticket
    changed: list[str]
    # Set by a coordinator edit: each changed field as `(from, to)`, as the field held it.
    moved: dict[str, tuple[Any, Any]] = {}


class TicketFilter(BaseModel):
    """Which tickets a list answers. `archived=None` answers both."""

    repository: str | None = None
    column: Column | None = None
    archived: bool | None = False
    parent: str | None = None
    label: str | None = None
    ids: list[str] | None = None


class TicketView(BaseModel):
    """A ticket as an agent starts on it: its fields, its document index, its latest history."""

    ticket: Ticket
    documents: list[DocumentInfo]
    recent_activity: list[Activity]


class TicketRef(BaseModel):
    """What another module needs to name a ticket: where it stands on the board."""

    id: str
    repository: str
    title: str
    column: Column
    labels: list[str]
    rank: int
    branch: str


class StageMove(BaseModel):
    """A ticket's arrival in a column."""

    at: datetime
    to: Column


class TicketFlow(BaseModel):
    """What the flow measures read of a ticket; its moves are oldest first."""

    id: str
    title: str
    stage: Column
    archived: bool
    branch: str
    created_at: datetime
    caused_by: list[str]
    moves: list[StageMove]


class TicketAddress(BaseModel):
    """A ticket named with the repository it belongs to; a ticket of another one is not found."""

    repository: str
    id: str


class TicketCore(Ticket):
    """A ticket as the unit of work reads it: its fields and whether it was deleted."""

    trashed: bool = False


class LinkGraph(BaseModel):
    """The tickets of a repository and each one's parent, for checking a link in one read."""

    ids: list[str]
    parent_of: dict[str, str]
