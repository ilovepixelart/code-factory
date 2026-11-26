"""The delivery module's shapes: pull requests as read, events, merge verdicts and errors."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr

from code_factory.platform.errors import ConflictError

PullState = Literal["", "open", "merged", "closed"]
Ci = Literal["none", "passed", "failed", "pending"]
EventKind = Literal[
    "ship_started",
    "ship_pushed",
    "ship_failed",
    "pull_request",
    "branch_pushed",
    "merged_pull_request",
    "merge_failed",
    "merge_base_unread",
    "retargeted_pull_request",
]
CHECKS_CONTEXT = "code-factory/checks"


class Frozen(BaseModel):
    """A value."""

    model_config = ConfigDict(frozen=True)


class PullReading(Frozen):
    """What GitHub says of one pull request, reduced."""

    state: PullState = ""
    review: str = ""
    ci: Ci = "none"
    other_ci: str = ""
    own_pending: bool = False
    head: str = ""
    base: str = ""
    draft: bool = False
    conflict: bool = False
    reviewed: str = ""
    merge_state: str = ""
    # The size GitHub counts, None when it gave no count: how much there is to review.
    additions: int | None = None
    deletions: int | None = None
    changed_files: int | None = None
    created_on_host: datetime | None = None
    updated_on_host: datetime | None = None
    merged_on_host: datetime | None = None
    first_review_at: datetime | None = None


class PullView(PullReading):
    """A recorded pull request of a ticket."""

    ticket_id: str
    repository: str
    url: str
    shipped_head: str = ""
    read_at: datetime
    since: datetime

    def as_card(self) -> dict[str, object]:
        """The board card's `pull`: the four keys always, the rest only when set."""
        card: dict[str, object] = {
            "state": self.state,
            "review": self.review,
            "ci": self.ci,
            "head": self.head,
            "url": self.url,
            "at": str(float(self.read_at.timestamp())),
        }
        optional = {
            "since": str(float(self.since.timestamp())),
            "base": self.base,
            "draft": self.draft,
            "conflict": self.conflict,
            "other_ci": self.other_ci,
            "own_pending": self.own_pending,
            "reviewed": self.reviewed,
        }
        card.update({key: value for key, value in optional.items() if value})
        sizes = {
            "additions": self.additions,
            "deletions": self.deletions,
            "changed_files": self.changed_files,
        }
        card.update({key: value for key, value in sizes.items() if value is not None})
        return card


class DeliveryEvent(Frozen):
    """One record of what delivery did to a ticket's pull request."""

    id: int = 0
    ticket_id: str
    kind: EventKind
    url: str = ""
    head: str = ""
    reason: str = ""
    by: str = ""
    from_base: str = ""
    to_base: str = ""
    retry_at: datetime | None = None
    at: datetime


class LiveRead(Frozen):
    """The pull request as read just before a merge."""

    state: str
    base: str
    head: str
    merge_state: str
    draft: bool = False
    base_error: str = ""


class MergeFacts(Frozen):
    """Everything the one merge rule decides on."""

    pull: PullView | None
    default_branch: str
    checks_configured: bool
    checked: Literal["passed", "failed", "missing"]
    events: tuple[DeliveryEvent, ...] = ()
    live: LiveRead | None = None


class MergeVerdict(Frozen):
    """The merge rule's answer: ready, or the sentence of the first failing guard."""

    ready: bool
    reason: str = ""
    record_base_unread: bool = False
    argv: tuple[str, ...] = ()


class Merged(Frozen):
    """A merge the board made."""

    url: str
    head: str


class ShipOutcome(Frozen):
    """What one ship of a ticket did."""

    ticket_id: str
    shipped: bool
    url: str = ""
    reason: str = ""


class PullHistory(Frozen):
    """A recorded pull request with when it opened and merged, as the factory measures them."""

    pull: PullView
    opened_at: datetime
    merged_at: datetime | None = None


class PassReport(Frozen):
    """What a delivery pass did, step by step."""

    steps: dict[str, str]


class NotReadyError(ConflictError):
    """The pull request cannot merge yet."""


class MergeRefusedError(ConflictError):
    """GitHub refused the merge."""


class TrackerItem(BaseModel):
    """An issue or message a tracker holds, to file as a ticket once: `url` names it."""

    url: str
    title: str
    body: str
    labels: list[str]
    kind: str
    priority: str
    due: str
    parent: str = ""
    """The link of its parent issue in the tracker; empty for none."""
    blocked_by: list[str] = []
    """The links of the tracker's issues that block it."""


class Tracker(BaseModel):
    """A tracker the repository takes tickets from: its kind, address, key and what to read."""

    model_config = ConfigDict(frozen=True)

    kind: str
    url: str
    key: SecretStr
    label: str = ""
    assigned: bool = False
    jql: str = ""
    email: str = ""
    channel: str = ""
    reaction: str = ""
