"""What the modules the team reads from answer: the shapes of its ports (see `service.ports`)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from code_factory.team.models.claims import TeamRun


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class ActiveRun(_Frozen):
    """A run with no exit and whether its process still lives; tokens are live for it."""

    run: TeamRun
    alive: bool


class RepositoryRef(_Frozen):
    """A tracked repository: its folder name and its path."""

    name: str
    path: str


class TicketAsk(_Frozen):
    """What a pick reads of a ticket: its type, its labels (comma separated) and repository."""

    kind: str
    labels: str = ""
    repository: str = ""


class TicketRef(_Frozen):
    """A ticket as a row names it."""

    repository: str
    id: str
    title: str


class TeamActivity(_Frozen):
    """One record of a ticket's history, with the words the ticket's view says of it."""

    at: float
    kind: str
    data: dict[str, Any] = Field(default_factory=dict)
    words: str = ""

    def text(self, key: str) -> str:
        """The value under `key` as text; empty when absent."""
        value = self.data.get(key)
        return "" if value is None else str(value)


class TicketFacts(_Frozen):
    """One ticket as the page reads it; `activities` run oldest first.

    `first_commit` is filled by the team service from git, not by the tickets module.
    """

    reference: TicketRef
    kind: str
    column: str
    column_since: float | None = None
    first_commit: float | None = None
    merged: float | None = None
    pull: tuple[str, str] | None = None
    pushed_without_pull: bool = False
    activities: tuple[TeamActivity, ...] = ()
    # The checks module's verdict on the pull request's head, the one the ticket page shows;
    # None while that head has none.
    check: bool | None = None


class OwnerItem(_Frozen):
    """One thing the inbox says waits on the owner: `questions`, `screens` or `stopped`."""

    ticket: TicketRef
    kind: str
    reason: str = ""
    since: float
    count: int = 1


class RunningGate(_Frozen):
    """A gate running on a ticket's tree, as the checks module reads it.

    `log` holds the `gate: ` lines of its log, `lock` the heavy-step lock's target
    (`<pid> <step> in <tree> on <branch>`) or `None`, `written_at` when the log last grew,
    `longest` the longest recorded pass of each step in seconds.
    """

    repository: str
    ticket_id: str
    tree: str
    started_at: float
    written_at: float
    log: str = ""
    lock: str | None = None
    longest: dict[str, float] = Field(default_factory=dict)


class AtWork(_Frozen):
    """A session's running subagent on a ticket."""

    agent_id: str
    ticket_id: str
    kind: str
    name: str
    doing: str
    since: float
    last_event_at: float


class LandJob(_Frozen):
    """A land job recorded running and whether its process lives."""

    ticket_id: str
    started_at: float
    alive: bool


class OpenChange(_Frozen):
    """An open pull request: its ticket, its label and the files its branch changes."""

    ticket_id: str
    label: str
    files: tuple[str, ...] = ()
