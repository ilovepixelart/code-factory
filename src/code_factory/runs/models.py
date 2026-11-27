"""DTOs of the runs module: a run, what the board shows of it, and what a start takes and gives."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# The review roles a repository may add (`[agents] review_roles`): each a run of its own before
# the review, read-only on the board.
ROLE_STAGES = ("qa", "security", "tests")
# A second reader of the Spec's documents and of a Build's plan, each opt-in.
READER_STAGES = ("read", "critique")
STAGES = ("spec", "build", "review", "split", "coordinate", *ROLE_STAGES, *READER_STAGES)
PERMISSION_MODES = ("acceptEdits", "bypassPermissions")
COORDINATOR = "coordinator"
STOPPED_CODE = -15  # SIGTERM as asyncio reports it
UNKNOWN_CODE = -1  # the run ended and nothing says how
TIMEOUT_CODE = -256  # the wrapper killed its group at the deadline
BUILD_UNVERIFIED_CODE = -257  # the board could not verify the build's output
BUILD_UNVERIFIED_REASON = "Build produced no verifiable committed changes"

RunState = Literal["running", "finished", "failed", "stopped", "limited"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Run(_Frozen):
    """One run of an agent: every column of the `runs` table.

    `exit_code` is `None` while the run is active, negative for a signal and -1 when the outcome
    is unknown. `commits` is `None` when none were recorded, which is not the same as none made.
    """

    id: str
    ticket_id: int | None = None
    ticket_key: str
    repository: str
    branch: str = ""
    worktree: str = ""
    log: str = ""
    stage: str
    pid: int | None = None
    pid_started_at: datetime | None = None
    started_at: datetime
    awake_started_at: datetime | None = None
    looping: bool = False
    permissions: str = "bypassPermissions"
    iteration: int = 1
    attempt: int = 0
    continued: bool = False
    exit_code: int | None = None
    ended_at: datetime | None = None
    settled_at: datetime | None = None
    cost: float | None = None
    cost_estimated: bool = False
    tokens: int | None = None
    cache_read: int | None = None
    turns: int | None = None
    halted: str = ""
    instructions: str = ""
    model: str = ""
    agent: str = ""
    connection: str = ""
    head: str = ""
    judged_head: str = ""
    tests_checked: bool = False
    uncommitted: bool = False
    commits: list[str] | None = None
    limited_until: datetime | None = None
    resume_refused: str = ""
    context: str = ""
    context_at: datetime | None = None
    memory_digest: str | None = None


class RunView(_Frozen):
    """What a board card and `list_runs` show of a run."""

    id: str
    ticket_id: str
    stage: str
    agent: str
    model: str
    state: RunState
    started_at: datetime
    ended_at: datetime | None = None
    exit_code: int | None = None
    halted: str = ""
    limited_until: datetime | None = None
    tokens: int | None = None
    cost: float | None = None
    cost_estimated: bool = False
    commits: list[str] | None = None
    uncommitted: bool = False


class Repair(_Frozen):
    """A scheduler repair bound to the branch head that needs it."""

    head: str
    reason: Literal["ci", "conflict"]
    task: str


class StartOptions(_Frozen):
    """How a start differs from the plain one.

    `tree` is a ready worktree name the follower hands over; `attempt` numbers parallel attempts.
    """

    looping: bool = False
    permissions: str = "bypassPermissions"
    iteration: int = 1
    attempt: int = 0
    prompt: str | None = None
    nudge: str | None = None
    tree: str | None = None
    repair: Repair | None = None


class Started(_Frozen):
    """The runs a start made: one per attempt under one claim."""

    runs: list[Run]


class Ended(_Frozen):
    """A run a collection pass ended: its limit when it hit one, whether it was stopped."""

    run: Run
    limit_until: datetime | None = None
    stopped: bool = False


class PermissionRequest(_Frozen):
    """A tool call an agent waits on the owner for."""

    id: str
    run_id: str | None = None
    repository: str
    ticket_key: str
    tool: str
    summary: str
    kind: str | None = None
    note: str = ""
    requested_at: datetime
    verdict: Literal["allow", "deny"] | None = None
    answered_at: datetime | None = None
    answered_by: str = ""
    status: Literal["pending", "answered", "expired", "withdrawn"] = "pending"


class PreviewStatus(_Frozen):
    """A ticket's live preview as the ticket page shows it."""

    configured: bool
    running: bool
    unavailable_reason: str | None = None
    port: int | None = None
    address: str | None = None
    started: datetime | None = None
    idle_seconds: int | None = None


class DayUsage(_Frozen):
    """One UTC day's usage by one agent on one model."""

    day: str
    agent: str
    model: str
    runs: int = 0
    tokens: int = 0
    cost: float = 0.0


class BudgetScope(_Frozen):
    """A budget a start is checked against: its name, the limit and what is spent."""

    name: Literal["ticket", "month"]
    budget: float
    spent: float
    month: str = ""


class RunCost(_Frozen):
    """The cost facts of an ended run the budget review reads."""

    id: str
    priced: bool
    cost: float | None = None
    ended: bool = True


class Decision(_Frozen):
    """One decision on a permission request."""

    at: datetime
    repository: str
    ticket_key: str
    tool: str
    decision: Literal["allow", "deny"]
    by: Literal["policy", "reviewer", "owner"]
    reason: str = ""


class Halt(_Frozen):
    """The stop of every agent: when and by whom."""

    halted_at: datetime
    by: str


class PreviewRecord(_Frozen):
    """A running preview: its process group (and when it started), port and ticket."""

    ticket_id: int
    repository: str
    pgid: int
    pgid_started_at: datetime
    port: int
    started_at: datetime


class Review(_Frozen):
    """What the configured reviewer said of one request; `input_sha256` names the call it saw."""

    at: datetime
    session_id: str
    ticket_key: str
    tool: str
    summary: str
    input_sha256: str
    verdict: Literal["allow", "deny", "owner"]


class ActiveRun(_Frozen):
    """A run with no exit and whether its process still lives."""

    run: Run
    alive: bool


class RunHooks(_Frozen):
    """The commands that start a run's hooks: ask before a tool, tell, recall, guard rewrites."""

    permission: str
    tell: str
    recall: str
    rewrite: str
