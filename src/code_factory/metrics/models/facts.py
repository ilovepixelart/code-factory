"""What this module reads from the others, in its own words.

Instants are `datetime`; the rules turn them into epoch seconds. A provider's adapter in
`module.py` renames its service's fields into these.
"""

from datetime import datetime
from pathlib import Path

from code_factory.metrics.models.base import Dto


class TrackedRepo(Dto):
    """A tracked repository: its name as tickets key it and its checkout."""

    name: str
    path: Path


class StageMove(Dto):
    """A ticket's arrival in a stage."""

    at: datetime
    to: str


class TicketFlow(Dto):
    """What the flow reads of a ticket; `moves` are oldest first, `branch` is empty when none."""

    id: str
    title: str
    stage: str
    archived: bool
    branch: str
    created_at: datetime
    caused_by: list[str]
    needs: str
    moves: list[StageMove]


class RunFacts(Dto):
    """One agent run. `commits` is None when none was recorded, never "it made none"."""

    repository: str
    ticket_id: str
    stage: str
    agent: str
    model: str
    connection: str
    started_at: datetime
    exit_code: int | None
    halted: str
    tokens: int | None
    cost: float | None
    cost_estimated: bool
    commits: list[str] | None


class CheckRecord(Dto):
    """The verdict of one run of the checks on a commit."""

    ticket_id: str
    commit: str
    exit_code: int | None
    at: datetime


class StepRun(Dto):
    """One recorded gate run: seconds of the steps that passed, the state of each step."""

    ticket_id: str
    at: datetime
    seconds: dict[str, int]
    states: dict[str, str]
    retried: list[str]
    lock_waits: dict[str, int]
    slept: bool
