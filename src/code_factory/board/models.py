"""What the board takes from other modules and what it answers that is not a plain dictionary.

Inputs are the facts a card is made of; each source module (runs, checks, delivery, sessions)
answers in these shapes, and the answers the web app reads are plain dictionaries built by the
rules, so a key a card does not have is absent rather than null.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from code_factory.platform.text.paging import Paging
from code_factory.tickets.models import Ticket


class _Fact(BaseModel):
    model_config = ConfigDict(frozen=True)


class Tagged(BaseModel):
    """A pre-serialised answer and its ETag: the board is read every few seconds, unchanged."""

    body: str
    etag: str


class CheckRecord(_Fact):
    """One run of a ticket's checks on a commit; a run that gave no verdict has no say."""

    commit: str
    exit_code: int
    at: str = ""
    tree: str = ""
    reason: str = ""
    log: str = ""


class ActivityRecord(_Fact):
    """One record of a ticket's history as the card rules read it, oldest first."""

    kind: str
    at: float
    data: dict[str, Any] = Field(default_factory=dict)

    def text(self, key: str) -> str:
        """A data value as text; empty when absent."""
        value = self.data.get(key)
        return "" if value is None else str(value)


class PullFacts(_Fact):
    """What the card shows of a pull request, as the delivery module last recorded it."""

    state: str = "open"
    review: str = ""
    ci: str = ""
    head: str = ""
    url: str = ""
    at: str = ""
    other_ci: str | None = None
    draft: bool | None = None
    conflict: bool | None = None
    since: str | None = None
    own_pending: bool = False
    additions: int | None = None
    deletions: int | None = None
    changed_files: int | None = None


class SessionFacts(_Fact):
    """A live session as the card chips need it."""

    session_id: str
    cwd: str
    branch: str
    state: str


class RunCard(_Fact):
    """An active run as the card lists it."""

    id: str
    stage: str
    iteration: int
    loop: bool
    max_iterations: int
    attempt: int
    agent: str
    started_at: float


class RunCost(_Fact):
    """What a ticket's runs cost: totals null when no run reported usage."""

    total: float | None = None
    review: float | None = None
    cache_read: float | None = None
    turns: int | None = None


class TicketRuns(_Fact):
    """A ticket's runs: the active ones, what they spent and why they stopped."""

    runs: list[RunCard] = Field(default_factory=list)
    spent: float | None = None
    spent_estimated: bool = False
    cost: RunCost = Field(default_factory=RunCost)
    halted: str = ""
    limited_until: float | None = None


class Placement(_Fact):
    """Where a ticket stands: the column shown, the column its evidence reaches, its pin."""

    stage: str
    evidence_stage: str
    declared: str = ""
    hold: dict[str, str] | None = None


class CardFacts(_Fact):
    """Everything one card is made of, gathered once for the whole board."""

    ticket: Ticket
    placement: Placement
    stage_since: str = ""
    repository_path: str = ""
    open_questions: int = 0
    open_blockers: list[str] = Field(default_factory=list)
    children: int = 0
    children_done: int = 0
    pull: PullFacts | None = None
    check: dict[str, Any] | None = None
    runs: TicketRuns = Field(default_factory=TicketRuns)
    repository_budget: float | None = None
    sessions: list[dict[str, str]] = Field(default_factory=list)
    subagents: list[dict[str, Any]] = Field(default_factory=list)
    delivery_event: dict[str, Any] | None = None
    checks_configured: bool = False
    queue: dict[str, str] = Field(default_factory=dict)


class OffBoardRow(_Fact):
    """A ticket off the board: archived by hand or released, and when it left."""

    repository: str
    id: str
    title: str
    type: str
    stage: str
    archived: bool
    priority: str = ""
    assignee: str = ""
    rank: int = 0
    archived_at: float = 0.0
    release: str = ""


class ArchiveQuery(_Fact):
    """What the Archive page asks: text to find, the order, which kind and the page."""

    q: str = ""
    sort: str = ""
    dir: str = ""
    show: str = ""
    paging: Paging | None = None


class RunRecord(_Fact):
    """What a run received: the memory version and when its context was given."""

    memory: dict[str, Any] | None = None
    context_at: float | None = None


class RepositoryFacts(_Fact):
    """What a repository's settings say that the board shows."""

    name: str
    path: str = ""
    budget_usd: float | None = None
    monthly_budget_usd: float | None = None
    checks_configured: bool = False
