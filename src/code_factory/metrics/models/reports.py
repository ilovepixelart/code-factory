"""What the service answers: the Flow page, the gate step times, the forecast and the yields.

Instants are epoch seconds, durations seconds, costs US dollars. `MergedRow.from_` is the key
`from` on the wire (`from` is a keyword).
"""

from typing import Any

from pydantic import ConfigDict, Field, model_serializer

from code_factory.metrics.models.base import Dto
from code_factory.metrics.models.delivery import Autonomy, ChecksVerdict


def _without(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    """`data` less each of `keys` whose value is None: the page leaves those keys out."""
    return {k: v for k, v in data.items() if not (k in keys and v is None)}


class MergedRow(Dto):
    """One merged pull request of the window."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", validate_by_name=True, serialize_by_alias=True
    )

    repository: str
    pull: int | None
    url: str | None
    branch: str
    ticket: str | None
    title: str
    at: float
    lead: float
    from_: str = Field(alias="from")
    autonomy: Autonomy
    cost: float | None = None
    cost_estimated: bool | None = None
    reverted: bool
    fixes: list[str]
    checks: ChecksVerdict

    @model_serializer(mode="wrap")
    def _present_when_costed(self, handler: Any) -> dict[str, Any]:  # noqa: ANN401  # pydantic's handler
        return _without(handler(self), "cost", "cost_estimated")


class LeadStats(Dto):
    """Lead time from filing to merge over the merges whose filing is known."""

    median: float | None
    p85: float | None
    p95: float | None
    count: int


class Completion(Dto):
    """Tickets whose build started in the window, and those of them merged."""

    started: int
    merged: int


class CostStats(Dto):
    """The median cost per merged ticket among those with a cost."""

    median: float | None
    estimated: bool
    count: int
    of: int


class AutonomyCounts(Dto):
    """Merged rows by class and the share built without a hand commit."""

    share: float | None
    autonomous: int
    assisted: int
    unknown: int


class Columns(Dto):
    """Median whole minutes in each column over the merged tickets of the window."""

    spec: float | None
    build: float | None
    review: float | None


class InFlightRow(Dto):
    """A ticket on a branch past the usual lead time; `age` is None when the cut is unknown."""

    repository: str
    id: str
    title: str
    stage: str
    age: float | None
    needs: str


class Ending(Dto):
    """How many runs ended for one reason."""

    reason: str
    count: int


class AgentRuns(Dto):
    """The runs of one agent on one model over one connection."""

    agent: str
    model: str
    connection: str
    runs: int
    finished: int
    failed: int
    stopped: int
    running: int
    endings: list[Ending]
    tokens: int | None
    cost: float | None
    estimated: bool | None = None

    @model_serializer(mode="wrap")
    def _estimated_only_when_true(self, handler: Any) -> dict[str, Any]:  # noqa: ANN401  # pydantic's handler
        return _without(handler(self), "estimated")


class FlowPage(Dto):
    """The answer of `GET /api/flow`."""

    range: str
    since: float
    now: float
    merged: list[MergedRow]
    lead: LeadStats
    completion: Completion
    cost: CostStats
    autonomy: AutonomyCounts
    columns: Columns
    in_flight: int
    stuck_after: float
    stuck: list[InFlightRow]
    agents: list[AgentRuns]


class StepTime(Dto):
    """One gate step over the runs read: its pass and fail rates, flakiness and lock wait."""

    step: str
    runs: int
    median: int | None
    slowest: int | None
    slowest_on: str | None
    passed: int
    failed: int
    flaky: int
    waited: int


class ColumnTime(Dto):
    """One ticket's whole minutes in spec, build and review, None for a column never entered."""

    ticket: str
    minutes: tuple[int | None, int | None, int | None]
    now: str


class TimesReport(Dto):
    """The gate step times with the columns and reverts since the oldest run read."""

    steps: list[StepTime]
    since: float | None
    columns: list[ColumnTime]
    merges: int
    reverted: int
    text: str


class Forecast(Dto):
    """In how many days the open tickets are done at 50 and 85 percent likelihood."""

    p50: int | None
    p85: int | None
    open: int
    sample: list[int]


class Yield(Dto):
    """How one agent on one model's merged work held up."""

    agent: str
    model: str
    runs: int
    unfinished: int
    merged: int
    held: int
    end_to_end: int
    median_intake_to_merge: float | None
    cost: float | None
