"""A review of a ticket's branch: its verdict, findings and where each stands."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["pass", "changes"]
Severity = Literal["blocker", "major", "minor", "nit"]


class Finding(BaseModel):
    """One thing a review found: where (a requirement, or a path and line) and what."""

    severity: Severity
    text: str = Field(max_length=1000)
    requirement_id: str = ""
    path: str = ""
    line: int = Field(default=0, ge=0)
    rule: str = ""
    prior_id: str = ""
    note_id: int | None = Field(default=None, gt=0)


class Review(BaseModel):
    """A review of a ticket's branch: the verdict, a summary and its findings."""

    verdict: Verdict
    summary: str = Field(max_length=1000)
    findings: list[Finding] = Field(default_factory=list, max_length=50)


class FindingId(BaseModel):
    """A finding as a submitted review numbered it."""

    id: str
    severity: Severity


class FindingDismissed(BaseModel):
    """A finding a Build run dismissed, with the reason it gave."""

    id: str
    reason: str


FindingStatus = Literal["open", "fixed", "dismissed"]


class FindingState(BaseModel):
    """A finding and where it stands; `reason` and `by` say how a closed one was closed.

    A blocker or major finding is `important` and sends a review back while open; the rest are
    nits. It is `class` on the wire.
    """

    id: str
    severity: Severity
    finding_class: Literal["important", "nit"] = Field(serialization_alias="class")
    file: str
    line: int
    text: str
    rule: str
    requirement: str
    state: FindingStatus
    reason: str
    by: str


class ReviewRecord(BaseModel):
    """One submitted review: its document version, verdict, moment and author."""

    version: int
    verdict: Verdict
    at: datetime
    by: str


class ReviewSubmitted(BaseModel):
    """What a review submission wrote: the review document's version and the findings' ids."""

    review_version: int
    findings: list[FindingId]
