"""Agents, runs and claims as the team rules read them, and what the rules answer about them.

Times are epoch seconds (`float`), as the answers the web app reads are.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Outcome = Literal[
    "running",
    "finished",
    "finished, over limit",
    "uncommitted",
    "uncommitted, over limit",
    "usage limit",
    "over limit",
    "stopped",
    "failed",
]
DoingState = Literal["working", "waiting", "over limit"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class TeamAgent(_Frozen):
    """A defined agent: the columns it works, what it takes, its limits and its model.

    `refusal` is the sentence of a failed model check, empty while the model is usable.
    """

    name: str
    roles: tuple[str, ...] = ()
    types: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    max_tokens: int | None = None
    max_seconds: int | None = None
    input_price: float | None = None
    output_price: float | None = None
    max_daily_usd: float | None = None
    paused_at: float | None = None
    runtime: str = ""
    connection: str = ""
    model: str = ""
    refusal: str = ""


class TeamRun(_Frozen):
    """One run of an agent on a ticket, as the rules read it.

    `agent` is empty for the default agent; `repository` is the repository's folder name.
    """

    id: str
    ticket_id: str
    repository: str = ""
    stage: str
    agent: str = ""
    started_at: float
    ended_at: float | None = None
    exit_code: int | None = None
    tokens: int | None = None
    cost: float | None = None
    halted: str = ""
    limited_until: float | None = None
    uncommitted: bool = False
    resume_refused: str = ""
    context_at: int | None = None

    @property
    def active(self) -> bool:
        """Whether the run has no exit yet."""
        return self.exit_code is None


@dataclass(frozen=True, slots=True)
class Lease:
    """A ticket's claim: the agent holding it (empty: the default agent) and the runs under it."""

    agent: str
    runs: tuple[str, ...]
    claimed_at: float
    beat_at: float


@dataclass(frozen=True, slots=True)
class Ask:
    """What picking an agent for one ticket reads: its key, stage, type, labels, runs and the time.

    `kind` and `labels` (comma separated) are what an agent's lists are matched against.
    `other_model` is `[agents] review_other_model`; `escalate` is `[agents] escalate`.
    """

    key: str = ""
    stage: str = ""
    kind: str = ""
    labels: str = ""
    runs: tuple[TeamRun, ...] = ()
    now: float = 0.0
    other_model: bool = False
    escalate: bool = False


class Usage(_Frozen):
    """What an agent's runs on one ticket used: tokens (`None` while unknown) and whole seconds."""

    tokens: int | None
    seconds: int


class Doing(_Frozen):
    """What a defined agent that is not idle is doing, on the ticket `id` of `repository`."""

    state: DoingState
    repository: str
    id: str
    usage: Usage | None = Field(default=None, exclude_if=lambda value: value is None)


class Last(_Frozen):
    """A defined agent's latest run: its ticket, column, when it ended and how, in a word.

    `until`, `refused` (when not empty) and `context_at` are left out of the answer when unset.
    """

    run: str
    repository: str
    id: str
    stage: str
    at: float
    outcome: Outcome
    until: float | None = Field(default=None, exclude_if=lambda value: value is None)
    refused: str = Field(default="", exclude_if=lambda value: value == "")
    context_at: int | None = Field(default=None, exclude_if=lambda value: value is None)


class LaneRun(_Frozen):
    """One run drawn on the Team page."""

    id: str
    repository: str
    ticket: str
    stage: str
    started_at: float
    ended_at: float | None
    outcome: Outcome


class Lane(_Frozen):
    """One agent's lane: what it does now and its runs of the window."""

    agent: str
    doing: Doing | None
    runs: tuple[LaneRun, ...]


class Chain(_Frozen):
    """One ticket's runs across lanes in start order and the seconds waited between them.

    `waited[i]` is the wait before run `i + 1`: 0 when they overlap, `None` while run `i` runs.
    """

    repository: str
    ticket: str
    runs: tuple[str, ...]
    waited: tuple[float | None, ...]


class Lanes(_Frozen):
    """The answer of `GET /api/team`."""

    since: float
    now: float
    lanes: tuple[Lane, ...]
    chains: tuple[Chain, ...]


class Claim(_Frozen):
    """The agent a run takes (`None` for the default agent) and the agents it passed over."""

    agent: TeamAgent | None
    lease_id: int | None = None
    passed_over: tuple[str, ...] = ()


class ClaimView(_Frozen):
    """One claim as the command line lists it."""

    ticket_id: str
    agent: str
    runs: tuple[str, ...]
    claimed_at: float
    beat_at: float
    holds: bool
