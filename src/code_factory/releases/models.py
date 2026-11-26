"""What the release service takes and answers."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ReleaseState(StrEnum):
    """Where a release is: derived from its columns, never stored."""

    DRAFT = "draft"
    PUBLISHED = "published"
    TAGGED = "tagged"


class ReleaseTicket(BaseModel):
    """A merged ticket as the notes list it: its id, title and type (`kind`)."""

    id: str
    title: str
    kind: str


class ReleaseView(BaseModel):
    """One release of a repository; `tickets` are the ids a published release names."""

    repository: str
    version: str
    state: ReleaseState
    notes: str
    drafted_at: datetime
    published_at: datetime | None
    tag_commit: str | None
    tagged_at: datetime | None
    tickets: list[str]


class ReleaseNaming(BaseModel):
    """The release that named a ticket: its version and when it was published."""

    version: str
    published_at: datetime
