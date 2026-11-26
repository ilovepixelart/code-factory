"""The Team page's answer (`GET /api/team/now`) and the facts it is assembled from.

Field order is the order of the answer's keys. `Peek.kind` serialises as `type`: dump with
`by_alias=True`.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from code_factory.team.models.sources import OwnerItem, TicketFacts, TicketRef

RowState = Literal["owner", "stale", "waiting", "working", "merged"]
ActorKind = Literal["agent", "session", "reviewer", "board", "gate", "owner"]
Stage = Literal["first_commit", "pull_request", "gate_pass", "merged"]
GateState = Literal["passed", "failed", "running", "not_run"]
MergeState = Literal["open", "conflict", "merged"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Actor(_Frozen):
    """Who a row's work belongs to."""

    kind: ActorKind
    name: str


class PullState(_Frozen):
    """A row's pull request: number and address, its gate and its merge state."""

    number: int
    url: str
    gate: GateState
    merge: MergeState


class Also(_Frozen):
    """A second line of a row: another state its ticket is in."""

    state: RowState
    actor: Actor
    line: str
    since: float
    until: float | None


class Row(_Frozen):
    """One row: its state, ticket, actor, what it does, since when and, once done, until when."""

    key: str
    state: RowState
    ticket: TicketRef | None
    actor: Actor
    line: str
    since: float
    until: float | None
    also: tuple[Also, ...]
    pull: PullState | None


class Groups(_Frozen):
    """The five groups, each in its order."""

    needs_you: tuple[Row, ...]
    waiting: tuple[Row, ...]
    working: tuple[Row, ...]
    done_today: tuple[Row, ...]
    stale: tuple[Row, ...]


class Counts(_Frozen):
    """How many rows each group holds."""

    needs_you: int
    waiting: int
    working: int
    done_today: int
    stale: int


class Median(_Frozen):
    """A median of seconds from filing (`None` with no ticket) and how many tickets it counts."""

    median: float | None
    count: int


class StageTimes(_Frozen):
    """One stage's median today and this cycle."""

    stage: Stage
    today: Median
    cycle: Median


class Milestone(_Frozen):
    """One milestone of a ticket: when it was reached and the cycle's median for its stage."""

    stage: Literal["filed", "first_commit", "pull_request", "gate_pass", "merged"]
    at: float | None
    cycle: float | None


class Event(_Frozen):
    """One event of a ticket in words."""

    at: float
    words: str


class Peek(_Frozen):
    """What the panel shows of a selected row's ticket."""

    kind: str = Field(serialization_alias="type")
    column: str
    milestones: tuple[Milestone, ...]
    events: tuple[Event, ...]


class Cycle(_Frozen):
    """Where this cycle starts and, in words, from what."""

    since: float
    from_: str = Field(serialization_alias="from")


class TeamNow(_Frozen):
    """The page's answer. `peek` is keyed by `<repository>/<id>`."""

    now: float
    today: float
    cycle: Cycle
    counts: Counts
    groups: Groups
    idle: tuple[str, ...]
    paused: tuple[str, ...]
    stages: tuple[StageTimes, ...]
    peek: dict[str, Peek]


@dataclass(frozen=True, slots=True)
class Worker:
    """One worker at work, or a gate waiting for the heavy-step lock.

    `key` is stable across reads, which keeps a selected row selected.
    """

    key: str
    repository: str
    ticket: str | None
    actor: Actor
    line: str
    since: float
    last_event: float
    alive: bool
    stale_after: float
    waiting: bool = False


@dataclass(frozen=True, slots=True)
class Facts:
    """Everything one read of the page gathered."""

    now: float
    today: float
    cycle: Cycle
    tickets: tuple[TicketFacts, ...] = ()
    workers: tuple[Worker, ...] = ()
    owner: tuple[OwnerItem, ...] = ()
    agents: tuple[str, ...] = ()
    paused: tuple[str, ...] = ()


@dataclass(slots=True)
class GateProgress:
    """What a running gate's log and the heavy-step lock say of it."""

    step: str | None = None
    started: bool = False
    holds_lock: bool = False
    waiting: bool = False
    behind: tuple[str, str] | None = None
    last_passed: str | None = None
