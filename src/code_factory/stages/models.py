"""What the stage rules and the stage service take and answer.

A stage is named by its lower-case word (`spec`, `build`, `review`, `merged`, and the off-board
`released`); the board's labels are in `rules.stage_label`.
"""

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from code_factory.platform.errors import BadRequestError


class Stage(StrEnum):
    """A board column, in the order a ticket walks them."""

    SPEC = "spec"
    BUILD = "build"
    REVIEW = "review"
    MERGED = "merged"


LANDED = frozenset({Stage.MERGED.value, "released"})
RELEASED = "released"


class _Value(BaseModel):
    model_config = ConfigDict(frozen=True)


class EvidenceItem(_Value):
    """What one stage needs, and whether it is there."""

    stage: str
    required: bool
    present: bool
    detail: str


class BranchFacts(_Value):
    """The git side of a ticket's evidence, as the observer last read it.

    `known=False` means git could not be read: nothing may act on the placement.
    """

    known: bool = False
    local: bool = False
    pushed: bool = False
    in_worktree: bool = False
    merged: bool = False
    has_commits: bool = False
    untraced: str = ""
    default_branch: str = "main"
    head: str = ""


class Record(_Value):
    """One entry of a ticket's activity ledger, as the fix loop reads it."""

    kind: str
    at: datetime
    data: Mapping[str, Any] = Field(default_factory=dict)

    def text(self, key: str) -> str:
        """The value of `key` as text, empty when absent."""
        value = self.data.get(key)
        return "" if value is None else str(value)


class PullView(_Value):
    """What the fix loop reads of a pull request."""

    state: str = "open"
    review: str = ""
    ci: str = "none"
    head: str = ""
    other_ci: str = ""
    own_pending: bool = False
    reviewed: str = ""
    url: str = ""


class MainCheckView(_Value):
    """One run of the checks on a repository's default branch."""

    exit_code: int
    step: str = ""

    @property
    def failed(self) -> bool:
        """Whether the run failed."""
        return self.exit_code != 0


class LogReading(_Value):
    """What a checks log says: where it failed and how the gate went."""

    failing_lines: list[str] = Field(default_factory=list)
    failing_tests: list[str] = Field(default_factory=list)
    build_failure: bool = False
    failure_reason: str = ""
    reported_steps: list[tuple[str, str]] = Field(default_factory=list)
    step_seconds: list[tuple[str, int]] = Field(default_factory=list)
    lock_waits: list[tuple[str, int]] = Field(default_factory=list)
    quarantined_failures: list[tuple[str, int]] = Field(default_factory=list)
    flaky_steps: list[str] = Field(default_factory=list)


RoundOutcome = Literal["started", "given", "halted", "waiting"]


class RoundDecision(_Value):
    """What `begin_fix_round` decided: `rounds` is how many the ticket has now."""

    outcome: RoundOutcome
    rounds: int = 0


class Hold(_Value):
    """Why a merge waits for a review; `owner` says the owner decides rather than a reviewer."""

    reason: str
    owner: bool


class StageAssessment(_Value):
    """Where a ticket stands and why, from its stored facts."""

    ticket_id: str
    number: int
    declared: str
    derived: str
    stage: str
    work_done: bool
    checklist: list[EvidenceItem]
    refusals: dict[str, str]
    hold: dict[str, str] | None
    landed: bool
    facts_known: bool
    git_unreadable: bool
    observed_at: datetime | None


class StageMove(_Value):
    """A move the service made: the stage before and after, and the pin before and after."""

    ticket_id: str
    number: int
    from_stage: str
    to_stage: str
    declared_before: str
    declared_after: str
    changed: bool


class PresenceChange(_Value):
    """A checklist item whose presence differs from its last record."""

    ticket_id: str
    stage: str
    present: bool


class ObserveReport(_Value):
    """What one observation pass did."""

    observed: int = 0
    unknown: int = 0
    changes: list[PresenceChange] = Field(default_factory=list)


class StageEvent(_Value):
    """One row of a ticket's stage history, from any of the module's tables."""

    at: datetime
    kind: str
    sentence: str


class EvidenceChange(_Value):
    """One `evidence_changes` row."""

    ticket_id: str
    stage: str
    present: bool
    at: datetime


class ChecksState(_Value):
    """What the board's checks on a head say."""

    exit_code: int | None
    settled: bool
    rerun_pending: bool
    container_retry_due: bool
    failed_steps: list[str] = Field(default_factory=list)


class FlakyReading(_Value):
    """A failure that makes a pass on its tree flaky, and the sentence that files it."""

    log: str
    reason: str


class FixRound(_Value):
    """One fix round a ticket was given."""

    head: str
    reason: str
    review: str
    run_id: str
    at: datetime


class FixHalt(_Value):
    """One head and reason the rounds ran out on."""

    head: str
    reason: str
    rounds: int
    at: datetime


class FixWait(_Value):
    """The step a head failed on that main fails too."""

    head: str
    step: str
    main_commit: str
    at: datetime


class BlockingFinding(_Value):
    """An open finding that sends a review back."""

    id: str
    severity: str
    text: str


class ReviewVerdict(_Value):
    """One review decision of the board: passed, returned or skipped."""

    run_id: str
    outcome: Literal["passed", "returned", "skipped"]
    head: str
    reason: str
    note: str
    at: datetime


class FixLedger(_Value):
    """A ticket's fix rounds, halts, waits and review verdicts, for the `stage rounds` command."""

    rounds: list[FixRound]
    halts: list[FixHalt]
    waits: list[FixWait]
    verdicts: list[ReviewVerdict]


ReviewDecision = Literal["pass", "changes", "halt"]


class ReviewOutcome(_Value):
    """What `apply_review` decided for an ended review run."""

    decision: ReviewDecision
    returned: int = 0
    sentence: str = ""


class MoveRefusedError(BadRequestError):
    """A move the board refuses; the message is the sentence that says why."""
