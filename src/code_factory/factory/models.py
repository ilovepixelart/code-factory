"""What the providers hand the factory (facts) and what the factory answers (figures).

Instants are epoch seconds, durations seconds, costs US dollars. An answer's `from` key is the
field `from_`, since `from` is a keyword.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

MAX_SAFE_JSON_INT = 2**53 - 1


class Frozen(BaseModel):
    """A value that never changes after it is built."""

    model_config = ConfigDict(frozen=True)


class PullState(StrEnum):
    """Where a pull request stands on its host."""

    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


class AutonomyClass(StrEnum):
    """Whether a merged pull request got a human code push."""

    AUTONOMOUS = "autonomous"
    ASSISTED = "assisted"
    UNKNOWN = "unknown"


class Component(StrEnum):
    """Which part of the work a run's cost belongs to."""

    SPEC = "spec"
    BUILD = "build"
    REVIEW = "review"
    OTHER = "other"


class Size(StrEnum):
    """A pull request's size by changed lines."""

    S = "S"
    M = "M"
    L = "L"
    XL = "XL"
    UNKNOWN = "unknown"


class RunFact(Frozen):
    """One agent run. `stage` is the run's stage, or `judge`, `eval`, `benchmark`, `improve`."""

    id: str
    ticket_id: str | None
    repository: str
    stage: str
    agent: str
    model: str
    source: str
    state: str
    started_at: float


class PullFact(Frozen):
    """One pull request, first observed at `opened_at`."""

    url: str
    repository: str
    number: int
    ticket_id: str | None
    title: str
    opened_at: float
    state: PullState
    merged_at: float | None = None
    first_review_at: float | None = None
    changed_lines: int | None = None
    autonomy: AutonomyClass = AutonomyClass.UNKNOWN
    ticket_pulls: int = 1
    closed_at: float | None = None


class RunCost(Frozen):
    """What one run cost; `cost` is None when the runtime reported none."""

    cost: float | None
    estimated: bool = False
    tokens: int | None = None


class ScorerCard(Frozen):
    """One scorer's answers over the window it was counted in."""

    repository: str
    name: str
    question: str
    yes: int
    no: int
    unclear: int
    average_score: float | None
    window_since: float
    window_until: float


class ScorerCards(Frozen):
    """The scorer provider's answer; `available` is False for a provider that is not built yet."""

    available: bool
    cards: list[ScorerCard] = Field(default_factory=list)


class ImprovementPR(Frozen):
    """One self-improvement pull request."""

    url: str
    number: int
    title: str
    state: PullState
    opened_at: float
    failures: int | None


class Improvements(Frozen):
    """The improvement provider's answer, newest first."""

    available: bool
    items: list[ImprovementPR] = Field(default_factory=list)


class Period(Frozen):
    """A half open range `[from_, to)` of instants, and the instant it was asked at."""

    from_: float = Field(serialization_alias="from")
    to: float
    now: float


class PrCounts(Frozen):
    """Pull request counts of a cohort; `merged_in_period` counts merges in the range."""

    opened: int
    merged: int
    merged_in_period: int
    open: int
    closed: int


class Cohort(Frozen):
    """The pull requests first observed in a range, one per url, and their counts."""

    members: list[PullFact]
    counts: PrCounts


class SeriesPoint(Frozen):
    """Pull requests opened in one bucket and how many of those merged."""

    start: float
    opened: int
    merged: int


class Series(Frozen):
    """Opened versus merged over time; `bucket` is `day` or `week`."""

    bucket: str
    points: list[SeriesPoint]


class Autonomy(Frozen):
    """Merged pull requests by autonomy; `unknown` is never in the share's denominator."""

    share: float | None
    autonomous: int
    assisted: int
    unknown: int


class Cycle(Frozen):
    """One merged pull request's durations; a stage that cannot be measured is None."""

    kickoff_to_pr: float | None
    pr_to_review: float | None
    review_to_merge: float | None
    total: float | None


class Spread(Frozen):
    """The median of the values that exist, and how many there were."""

    median: float | None
    count: int


class StageSpread(Frozen):
    """A cycle stage's spread."""

    stage: str
    median: float | None
    count: int


class CycleSummary(Frozen):
    """Cycle time of the merged cohort; stage medians do not add up to the total."""

    total: Spread
    stages: list[StageSpread]


class PrCost(Frozen):
    """What one pull request cost: its ticket's runs started before it ended, split evenly."""

    pull: PullFact
    state: PullState
    cost: float | None
    complete: bool
    estimated: bool
    runs: int
    by_component: dict[Component, float]


class ComponentCost(Frozen):
    """One component's median per priced pull request and its total."""

    component: Component
    median: float | None
    total: float


class SizeCost(Frozen):
    """One size's median cost, with how many of its pull requests were priced."""

    size: Size
    median: float | None
    priced: int
    of: int


class CostSummary(Frozen):
    """Cost per pull request over a cohort, and what measurement runs spent."""

    median: float | None
    priced: int
    of: int
    estimated: bool
    measurement: float | None
    by_component: list[ComponentCost]
    by_size: list[SizeCost]


class OwnerTime(Frozen):
    """An owner's recorded active time and USD hourly rate for one pull request."""

    model_config = ConfigDict(extra="forbid", strict=True)
    pull_url: str = Field(min_length=1, max_length=2048)
    active_minutes: int = Field(ge=0, le=MAX_SAFE_JSON_INT)
    hourly_rate_usd: float = Field(ge=0, le=MAX_SAFE_JSON_INT)


class MergedCost(Frozen):
    """Median including owner time, over merges with a time entry and complete run costs."""

    median: float | None
    priced: int
    owner_recorded: int
    merged: int
    estimated: bool


class KeyCount(Frozen):
    """Runs sharing one value of a breakdown key."""

    key: str
    runs: int


class RunBreakdowns(Frozen):
    """Runs of a range counted by stage, state, source, model and agent."""

    total: int
    by_stage: list[KeyCount]
    by_state: list[KeyCount]
    by_source: list[KeyCount]
    by_model: list[KeyCount]
    by_agent: list[KeyCount]


class ExpensivePr(Frozen):
    """A priced pull request in the list of the most expensive."""

    url: str
    repository: str
    number: int
    ticket: str | None
    title: str
    state: PullState
    opened_at: float
    cost: float
    cost_complete: bool
    estimated: bool
    changed_lines: int | None
    size: Size
    runs: int


class Window(Frozen):
    """The instants a scorer card was counted over."""

    from_: float = Field(serialization_alias="from")
    to: float


class ScorerView(Frozen):
    """A scorer card as the page shows it."""

    repository: str
    name: str
    question: str
    yes: int
    no: int
    unclear: int
    asked: int
    pass_rate: float | None
    average_score: float | None
    window: Window


class Scorers(Frozen):
    """The scorer cards of a range."""

    available: bool
    cards: list[ScorerView]


class ExpensiveList(Frozen):
    """The answer of `/api/factory/prs/expensive`."""

    prs: list[ExpensivePr]


class FixRoundOutcome(Frozen):
    """PR outcomes grouped by the number of repair requests the board recorded."""

    rounds: int
    merged: int
    closed: int
    open: int
    merge_rate: float | None


class RoleNoteOutcome(Frozen):
    """Notes a review role posted and notes linked to findings marked fixed."""

    role: str
    notes: int
    fixed: int


class Dashboard(Frozen):
    """Everything the factory page shows for one range."""

    from_: float = Field(serialization_alias="from")
    to: float
    now: float
    runs: RunBreakdowns
    prs: PrCounts
    series: Series
    autonomy: Autonomy
    cycle: CycleSummary
    cost: CostSummary
    merged_cost: MergedCost
    expensive: list[ExpensivePr]
    scorers: Scorers
    improvements: Improvements
    fix_rounds: list[FixRoundOutcome] = Field(default_factory=list)
    role_notes: list[RoleNoteOutcome] = Field(default_factory=list)
