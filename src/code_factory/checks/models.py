"""What the checks module takes and answers: enums and values, no IO."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

CHECKS_CONTEXT = "code-factory/checks"
MAIN = "main"  # the subject of a run on the default branch, where a ticket's id would be
NO_VERDICT_CODES = frozenset({-1, 137})
FIX_CHECK_REQUEST = "review-fix"


class _Value(BaseModel):
    model_config = ConfigDict(frozen=True)


class Scope(StrEnum):
    """Which command a run takes: `[checks] fast`, `[checks] command` or `[checks] main`."""

    FAST = "fast"
    REACHED = "reached"
    FULL = "full"


class Containment(StrEnum):
    """How a run is kept from the machine."""

    NONE = "none"
    SRT = "srt"
    CONTAINER = "container"


class RunState(StrEnum):
    """Where a run of `check_runs` stands."""

    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    LOST = "lost"


class Verdict(StrEnum):
    """What a finished run says of the code; no verdict says nothing."""

    PASSED = "passed"
    FAILED = "failed"
    NO_VERDICT = "no_verdict"


class ViewState(StrEnum):
    """The state `latest` answers."""

    NONE = "none"
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    NO_VERDICT = "no_verdict"


class Judged(_Value):
    """What a run judged: the commit checked out, the name of its tree and its tree id.

    `tracked` names the commit and its tracked changes only: files a command creates (caches,
    build output) leave it as it was.
    """

    head: str
    tree: str
    tree_id: str = ""
    tracked: str = ""


class Phases(_Value):
    """Where a run's time went, read from its log, in seconds."""

    heavy_wait: float = 0.0
    compile: float = 0.0
    tests: float = 0.0
    scope: str | None = None


class CheckRun(_Value):
    """One run of the checks: the queue, the container turn and the heartbeat in one row."""

    id: int
    repository: str
    subject: str
    scope: Scope
    commit: str
    tree_id: str
    state: RunState
    contained: Containment
    owner: str
    requested_by: str
    queued_at: datetime
    started_at: datetime | None
    beat_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    verdict: Verdict | None
    log_path: str
    workspace: str = ""


class ChecksView(_Value):
    """The latest run of a ticket and a page of its log."""

    state: ViewState
    check_id: int | None = None
    commit: str = ""
    head_current: bool = False
    exit_code: int | None = None
    failed_step: str = ""
    reason: str = ""
    finished_at: datetime | None = None
    log_tail: str = ""
    log_offset: int = 0
    log_size: int = 0
    next_offset: int = 0


class CheckRecord(_Value):
    """A `checks` record of a ticket."""

    ticket_id: str = ""
    at: datetime
    commit: str
    exit_code: int | None
    tree: str = ""
    tree_id: str = ""
    log: str = ""
    reason: str = ""


class StepRun(_Value):
    """What one `checks` record says of its steps."""

    ticket_id: str
    at: datetime
    seconds: dict[str, int] = Field(default_factory=dict)
    states: dict[str, str] = Field(default_factory=dict)
    retried: list[str] = Field(default_factory=list)
    lock_waits: dict[str, int] = Field(default_factory=dict)
    slept: bool = False


class MainRecord(_Value):
    """The latest run on a repository's default branch."""

    repository: str
    commit: str
    exit_code: int
    log: str
    at: datetime
    step: str = ""
    passed: str = ""
    broken_by: str = ""
    searched: bool = False
    reason: str = ""

    @property
    def failed(self) -> bool:
        """Whether the run failed."""
        return self.exit_code != 0


class MainFailure(_Value):
    """A failing run on a default branch as the inbox shows it."""

    repository: str
    commit: str
    step: str
    reason: str
    exit_code: int
    log: str
    tail: str
    passed: str
    broken_by: str
    ticket: str
    at: datetime


class ReleaseRef(_Value):
    """The newest release a verification is due for."""

    version: str
    at: datetime
    tickets: list[str] = Field(default_factory=list)


class VerifyRecord(_Value):
    """One run of `[release] verify`."""

    id: int
    repository: str
    release: str
    at: datetime
    exit_code: int
    log: str
    ticket: str = ""


class PullHead(_Value):
    """An open pull request's head, as the forge says it."""

    repository: str
    ticket_id: str
    head: str


class Claim(_Value):
    """A check handed to a runner."""

    repository: str
    id: str
    head: str
    tree_id: str


class RunnerResult(_Value):
    """What a runner reports of a check."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    head: str
    tree_id: str
    exit_code: int
    log_tail: str = ""


class CacheFolder(_Value):
    """A ticket's build cache folder."""

    name: str
    path: str


class PruneReport(_Value):
    """What a prune lists, or removed."""

    logs: list[str] = Field(default_factory=list)
    caches: list[str] = Field(default_factory=list)
    runs: int = 0


class Action(_Value):
    """What the kill policy says to do after a run ended."""

    rerun: bool
    record_kill: dict[str, Any] | None = None
    kills: list[dict[str, Any]] = Field(default_factory=list)


class Ran(_Value):
    """How one attempt of the checks command ended, as the kill policy reads it."""

    code: int
    log: str
    killed: bool
    step: str | None = None


class BugDraft(_Value):
    """The bug a failing release verification files."""

    title: str
    type: str
    labels: list[str]
    priority: str
    caused_by: list[str]
    description: str
