"""What the evals module takes and answers: enums and values, no IO."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    """Values are compared and shared, never edited."""

    model_config = ConfigDict(frozen=True)


class Kind(StrEnum):
    """What a suite run measures."""

    BUILD = "build"
    REVIEW = "review"


class Stage(StrEnum):
    """The stage whose agent a task set measures."""

    SPEC = "spec"
    BUILD = "build"
    REVIEW = "review"


class Role(StrEnum):
    """What a task run is: a build task, a review of an escape, a review of a clean change."""

    BUILD = "build"
    ESCAPE = "escape"
    CLEAN = "clean"


class Answer(StrEnum):
    """What a scorer's agent answers."""

    YES = "yes"
    NO = "no"
    UNCLEAR = "unclear"


class StartedBy(StrEnum):
    """Who asked for a judging: the owner on the command line, or the daily pass."""

    OWNER = "owner"
    SCHEDULE = "schedule"


class JudgementKind(StrEnum):
    """The two row shapes of `eval_judgements`."""

    SCORE = "score"
    ANSWER = "answer"


class BuildTask(Frozen):
    """A `[[task]]` of a build set: a prompt, a base commit and the command that proves it."""

    id: str
    base: str
    prompt: str
    check: str


class ReviewTask(Frozen):
    """A `[[review]]` entry: a change to review. `files` is None for a clean change."""

    id: str
    ticket: str
    base: str
    head: str
    files: tuple[str, ...] | None = None
    defect: str = ""


class TaskSet(Frozen):
    """A parsed `.code-factory/evals/<set>.toml`."""

    stage: Stage
    tasks: tuple[BuildTask, ...] = ()
    reviews: tuple[ReviewTask, ...] = ()


class Merge(Frozen):
    """A first-parent merge into the default branch: its commit and its two parents."""

    sha: str
    base: str
    head: str
    branch: str


class TicketFacts(Frozen):
    """What the eval rules read of a ticket."""

    id: str
    title: str = ""
    description: str = ""
    branch: str = ""
    caused_by: tuple[str, ...] = ()


class Setup(Frozen):
    """What a record measured; an empty field equals an absent one."""

    stage: str = "build"
    runtime: str = ""
    model: str = ""
    instructions: str = ""
    memory: bool = False
    lesson: str = ""
    agent: str = ""
    connection: str = ""


class TaskRun(Frozen):
    """One run of one task: `passed` for a build or escape run, `blocking` for a clean run."""

    task_id: str
    run_no: int
    role: Role
    passed: bool | None = None
    blocking: int | None = None


class EvalRecord(Frozen):
    """One suite run, as recorded."""

    id: int = 0
    repository: str
    set_name: str
    kind: Kind
    recorded_at: datetime
    setup: Setup
    runs: int
    pass_at_1: float | None = None
    pass_k: float | None = None
    pass_at_k: float | None = None
    caught: float | None = None
    false_findings: float | None = None
    failed: int | None = None
    cost: float = 0.0
    tokens: int | None = None
    task_runs: tuple[TaskRun, ...] = ()


class Comparison(Frozen):
    """The lines of a comparison and whether the candidate loses (or has nothing to compare)."""

    lines: tuple[str, ...]
    loses: bool


class EscapeReport(Frozen):
    """What `add_escapes` added and each bug it skipped with the reason."""

    added: int = 0
    skipped: tuple[tuple[str, str], ...] = ()


class Finding(Frozen):
    """One finding of a review run."""

    severity: str
    path: str = ""
    line: int = 0
    text: str = ""


class ReviewOutcome(Frozen):
    """What one review run scored."""

    caught: bool
    blocking: int


class LessonVerdict(Frozen):
    """What `judge_lesson` decided."""

    lines: tuple[str, ...]
    loaded: bool


class Scorer(Frozen):
    """A yes or no question asked of sessions, from `[[scorers]]`."""

    name: str
    question: str
    stage: str = ""
    sample: float = 1.0
    threshold: int = 10


class AnswerRow(Frozen):
    """A recorded scorer answer."""

    session_id: str
    scorer: str
    answer: Answer
    evidence: str
    at: datetime


class Filed(Frozen):
    """A ticket a scorer filed: its source (`scorer:<name>@<epoch>`), whether it is open."""

    source: str
    open: bool
    id: str


class Counts(Frozen):
    """Answers in a window."""

    yes: int = 0
    no: int = 0
    unclear: int = 0


class ScorerFiring(Frozen):
    """A ticket a scorer is due to file; the follower files it."""

    scorer: str
    title: str
    body: str
    source: str
    kind: str = "bug"
    label: str = "scorer"


class ScorerRow(Frozen):
    """One line of the Agents page's Scorers table."""

    repository: str
    name: str
    question: str
    stage: str
    sample: float
    threshold: int
    week: Counts
    month: Counts
    ticket: str


class Judged(Frozen):
    """A judged session."""

    session: str
    score: int
    findings: tuple[str, ...]


class Asked(Frozen):
    """A scorer's answer about a session."""

    session: str
    scorer: str
    answer: Answer


class JudgingResult(Frozen):
    """The lines a judging printed, whether any session failed, whether the budget stopped it."""

    lines: tuple[str, ...] = ()
    failed: int = 0
    stopped: bool = False


class SessionEnd(Frozen):
    """A session and its last event."""

    session_id: str
    last_event_at: float


class RecurringFailure(Frozen):
    """A check step that failed the same way in several sessions."""

    step: str
    code: int
    sessions: tuple[str, ...]
    statement: str


class MemoryDraft(Frozen):
    """A memory entry the module proposes."""

    kind: str
    statement: str
    source: str
    why: str


class MemoryProposal(Frozen):
    """The memory module's merge or retire proposal."""

    action: str
    name: str
    into: str = ""
    guard: str = ""


class MemoryPair(Frozen):
    """Two entries that may contradict or share a subject."""

    kind: str
    one: str
    other: str
    topics: tuple[str, ...] = ()


class Consolidation(Frozen):
    """What memory proposes to merge, retire and decide."""

    proposals: tuple[MemoryProposal, ...] = ()
    pairs: tuple[MemoryPair, ...] = ()
