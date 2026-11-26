"""Merged pull requests and stage timelines: the git side of delivery facts."""

from enum import StrEnum

from code_factory.metrics.models.base import Dto


class Autonomy(StrEnum):
    """How a merged ticket was built."""

    AUTONOMOUS = "autonomous"
    ASSISTED = "assisted"
    UNKNOWN = "unknown"


class ChecksVerdict(StrEnum):
    """What the checks said of the commit a merge brought in."""

    PASSED = "passed"
    FAILED = "failed"
    NONE = "none"


class Transition(Dto):
    """The moment a ticket's stage became `stage`, in epoch seconds."""

    at: float
    stage: str


class Merge(Dto):
    """One pull request merged into a default branch, as the log shows it."""

    commit: str
    head: str
    pull: int | None
    branch: str
    ticket: str | None
    at: float
    started: float


class MergeFact(Merge):
    """A merge as the ledger holds it."""

    repository: str
    reverted: bool
    autonomy: Autonomy
    checks: ChecksVerdict


class RefreshResult(Dto):
    """What one pass over a repository did."""

    repository: str
    seen: int
    inserted: int
    reverted: int
    cuts: int
