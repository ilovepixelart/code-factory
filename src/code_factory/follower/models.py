"""The follower's shapes: queue cards, plans, active runs and a pass report."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    """A value."""

    model_config = ConfigDict(frozen=True)


class Card(Frozen):
    """What the queue reads of a ticket.

    `failures` counts its newest ended runs that failed in a row, `last_end` is when its newest
    ended run ended, `limited_until` when the usage limit that run ended on lifts.
    """

    id: str
    repository: str
    stage: str
    priority: str = ""
    rank: int = 0
    archived: bool = False
    blocked: str = ""
    work_done: bool = False
    runs: int = 0
    unanswered: int = 0
    halted: str = ""
    open_blockers: tuple[str, ...] = ()
    budget: float | None = None
    spent: float = 0.0
    review_due: bool = False
    fix_due: bool = False
    kind: str = "feature"
    labels: str = ""
    failures: int = 0
    last_end: datetime | None = None
    limited_until: datetime | None = None
    run_stage: str = ""
    """The stage its next run takes when it is not `stage`: a review role due before the review."""
    build_gaps: tuple[str, ...] = ()
    """What its requirements and spec lack before a Build run may start (`build_gaps`)."""


class ActiveRunFact(Frozen):
    """A run the caps count: its repository, ticket and stage, and whether it is still going."""

    repository: str
    ticket_id: str
    stage: str
    active: bool


class Planned(Frozen):
    """A queued ticket and the cap that holds it, `''` when it starts."""

    id: str
    reason: str


class PassReport(Frozen):
    """What each step of a pass did, or the error it ended with."""

    steps: dict[str, str]
