"""The inbox page: items, sections and the counts."""

from typing import Any

from pydantic import BaseModel, ConfigDict

SECTIONS = (
    "main", "questions", "permissions", "rules", "memory", "sessions", "stopped", "screens",
    "mergeable", "failing", "idle", "reviews", "diagnoses",
)  # fmt: skip
COUNTED = (
    "main",
    "questions",
    "permissions",
    "screens",
    "sessions",
    "stopped",
    "failing",
    "mergeable",
    "idle",
)


class TicketRef(BaseModel):
    """The ticket an item is about."""

    model_config = ConfigDict(frozen=True)

    repository: str
    id: str
    title: str


class Item(BaseModel):
    """One thing waiting on the owner, in the shape the Inbox page reads."""

    since: float | None = None
    kind: str = ""
    reason: str = ""
    note: str = ""
    count: int = 0
    images: list[str] = []
    ticket: TicketRef | None = None
    question: dict[str, Any] | None = None
    session: dict[str, Any] | None = None
    request: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None
    main: dict[str, Any] | None = None
    diagnosis: dict[str, Any] | None = None
    size: dict[str, int] | None = None
    """A pull request's lines added and deleted and files changed, when GitHub counted them."""


Sections = dict[str, list[Item]]


class PushFailure(BaseModel):
    """The last push that failed."""

    at: float
    problem: str


class PushState(BaseModel):
    """Where items are pushed, and the last failure."""

    host: str
    failure: PushFailure | None = None


class NextUp(BaseModel):
    """The oldest counted item: the one to answer first."""

    section: str
    index: int


class InboxPage(BaseModel):
    """`GET /api/inbox`: each section oldest first, the count, the newest sentence, next up."""

    main: list[Item]
    questions: list[Item]
    permissions: list[Item]
    rules: list[Item]
    memory: list[Item]
    sessions: list[Item]
    stopped: list[Item]
    screens: list[Item]
    mergeable: list[Item]
    failing: list[Item]
    idle: list[Item]
    reviews: list[Item]
    diagnoses: list[Item]
    count: int
    latest: str
    push: PushState | None = None
    next_up: NextUp | None = None


class InboxCount(BaseModel):
    """`GET /api/inbox/count`: how many items wait on a reply, and the newest sentence."""

    count: int
    latest: str
