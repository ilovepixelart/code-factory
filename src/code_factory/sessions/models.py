"""The sessions module's data: captured events, derived session views and their answers.

Pure: no IO, no framework. Times are seconds since the epoch as floats, which is what the answers
carry; the tables store `timestamptz` and the repository converts at the edge.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from code_factory.platform.errors import BadRequestError

type JsonAnswer = dict[str, object] | list[dict[str, object]]

STATE_REFUSED = "state must be one of waiting, working, idle, stale"
# The agent's own hook names: the events the ledger keeps and the install writes.
HOOK_EVENTS = (
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "Notification",
    "SubagentStart",
    "SubagentStop",
    "Stop",
)


class SessionState(StrEnum):
    """What a session is doing, before the clock is applied (`ended` also by the clock)."""

    WORKING = "working"
    IDLE = "idle"
    BLOCKED = "blocked"
    ENDED = "ended"


class StateFilter(StrEnum):
    """The state a Sessions query keeps, as the page's chips name them.

    A blocked session is `waiting`, a working one silent past the stale limit is `stale`; an ended
    session has none.
    """

    WAITING = "waiting"
    WORKING = "working"
    IDLE = "idle"
    STALE = "stale"

    @classmethod
    def from_text(cls, text: str) -> StateFilter:
        """The filter a query names.

        Raises:
            BadRequestError: `text` is not one of the four names.
        """
        try:
            return cls(text)
        except ValueError:
            raise BadRequestError(STATE_REFUSED) from None


@dataclass(frozen=True, slots=True)
class Event:
    """One captured hook payload, as the ledger stores it."""

    seq: int
    session_id: str
    agent_id: str | None
    event: str
    captured_at: float
    spool: str
    offset: int
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NewEvent:
    """A spool line that is an event, before the ledger gives it a `seq`."""

    spool: str
    offset: int
    session_id: str
    agent_id: str | None
    event: str
    captured_at: float
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class Reject:
    """A spool line that is no event: skipped once, kept for the person to see."""

    spool: str
    offset: int
    reason: str
    head: str


class Action(BaseModel):
    """A tool call that has started."""

    model_config = ConfigDict(frozen=True)

    tool: str
    summary: str
    started_at: float
    tool_use_id: str | None = None


class AgentView(BaseModel):
    """One subagent of a session."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    agent_type: str
    running: bool
    # Set by `settle`, never by the events.
    stale: bool = False
    current_action: Action | None = None
    last_event_at: float
    ticket: str | None = None
    started_at: float


class SessionView(BaseModel):
    """What a session is doing. The stored one is unsettled (no clock); readers settle it."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    cwd: str
    repository: str = ""
    branch: str = ""
    state: SessionState
    last_event_at: float
    stale: bool = False
    current_action: Action | None = None
    subagents: list[AgentView] = []
    last_prompt: str = ""
    turn_started_at: float | None = None
    turn_tool_calls: int = 0
    transcript: str = ""
    plan: str | None = None
    last_call: Action | None = None


class AtWork(BaseModel):
    """A running subagent of a live session that works on a ticket."""

    model_config = ConfigDict(frozen=True)

    ticket: str
    session_id: str
    agent_id: str
    name: str
    kind: Literal["session", "reviewer"]
    doing: str
    since: float
    last_event_at: float

    def fresh(self, now: float, within: float = 600.0) -> bool:
        """Whether its last event is at most `within` seconds before `now`."""
        return now - self.last_event_at <= within


@dataclass(frozen=True, slots=True)
class Checkout:
    """The repository a folder belongs to and the branch checked out there."""

    repository: str
    branch: str


@dataclass(frozen=True, slots=True)
class Usage:
    """Tokens by kind and the latest reported cost with when it was reported."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost: float | None = None
    reported_at: float | None = None
    cost_incomplete: bool = False


@dataclass(frozen=True, slots=True)
class Request:
    """One model request a run reported."""

    input: int
    output: int


@dataclass(frozen=True, slots=True)
class ReportedTokens:
    """The tokens the requests of one run reported."""

    input: int
    output: int


@dataclass(frozen=True, slots=True)
class Failure:
    """One failed check step: its name and exit code, as the gate prints them."""

    step: str
    code: int


@dataclass(frozen=True, slots=True)
class Recurrence:
    """A failure seen in several sessions."""

    failure: Failure
    sessions: list[str]


@dataclass(frozen=True, slots=True)
class IngestResult:
    """What one ingest pass took from the spool."""

    lines: int = 0
    rejects: int = 0
    sessions: int = 0


@dataclass(frozen=True, slots=True)
class PruneReport:
    """What pruning old spools removes (or would remove)."""

    spools: int = 0
    events: int = 0
    rejects: int = 0
    bytes: int = 0
    run_requests: int = 0


@dataclass(frozen=True, slots=True)
class HookSpec:
    """The command that records one hook event, and the events it is installed on."""

    command: str
    events: tuple[str, ...] = HOOK_EVENTS
    asynchronous: bool = True
